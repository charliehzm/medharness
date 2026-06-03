package middleware

// MedHarness §D.1 compliance gate (BE-7.1 · core spine).
//
// Order (non-streaming): phi-detect -> desensitize -> sign tier -> model-router
// -> injection -> base relay. Fail-closed: any gate deny / transport error /
// timeout / HTTP>=400 -> abort with a generic body, NO c.Next() (no upstream
// call, no cache write, no upstream log).
//
// Zero-trust tier (B1): the gate (this middleware) is the ONLY signer of
// tier_sig; model-router rejects any caller-asserted tier. signTier MUST stay
// byte-for-byte compatible with mcp/model-router/tier_trust.py.
//
// See docs/system-design/01-architecture.md §4 (§D.1) +
// docs/architecture/ADR-18-gateway-control-plane.md §2/§3/§4.
//
// TODO(BE-7.3): enforce that the base layer only fans out within
// RouteDecision.allowed_model_set.

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/gin-gonic/gin"
)

const complianceGateTimeout = 3 * time.Second

// tierFields MUST match mcp/model-router/tier_trust.py TIER_FIELDS exactly
// (order + names). Changing this breaks B1 signature verification.
var tierFields = []string{
	"model_id",
	"agent_role",
	"data_level",
	"change_id",
	"caller_vendor_family",
	"desensitized",
}

func complianceEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// signTier replicates tier_trust.sign_tier: HMAC-SHA256 hex over a canonical
// string built as "\n".join("<key>=<value>") for each TIER_FIELDS entry, where a
// missing value is "" and booleans are the strings "true"/"false".
func signTier(payload map[string]string, secret []byte) string {
	parts := make([]string, 0, len(tierFields))
	for _, k := range tierFields {
		parts = append(parts, k+"="+payload[k])
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(strings.Join(parts, "\n")))
	return hex.EncodeToString(mac.Sum(nil))
}

// gateOutcome: ok=false means a transport error/timeout (fail-closed);
// denied=true means the gate explicitly denied (or returned HTTP>=400 / an
// error body / decision=="deny").
type gateOutcome struct {
	body   map[string]any
	denied bool
	ok     bool
}

func callComplianceGate(client *http.Client, url string, payload []byte) gateOutcome {
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return gateOutcome{ok: false}
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return gateOutcome{ok: false}
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return gateOutcome{denied: true, ok: true}
	}
	var parsed map[string]any
	_ = common.Unmarshal(raw, &parsed)
	if parsed != nil {
		// MCP deny signals are not uniform across the spine: model-router uses
		// decision="deny", outbound-safety uses decision="blocked", and the
		// injection scanner uses a top-level boolean "blocked": true (HTTP 200,
		// no "decision"). Honor all of them, or those §D.1 gates are no-ops and
		// injection attacks / unsafe responses pass through to the client.
		if decision, _ := parsed["decision"].(string); decision == "deny" || decision == "blocked" {
			return gateOutcome{body: parsed, denied: true, ok: true}
		}
		if blocked, _ := parsed["blocked"].(bool); blocked {
			return gateOutcome{body: parsed, denied: true, ok: true}
		}
		if _, hasErr := parsed["error"]; hasErr {
			return gateOutcome{body: parsed, denied: true, ok: true}
		}
	}
	return gateOutcome{body: parsed, ok: true}
}

func abortCompliance(c *gin.Context) {
	c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{
		"error": gin.H{
			"code": "compliance_gate_denied",
			"msg":  "request denied by compliance gate",
		},
	})
}

func writeGenericCompliance503(w gin.ResponseWriter) {
	header := w.Header()
	for key := range header {
		delete(header, key)
	}
	body, _ := common.Marshal(gin.H{
		"error": gin.H{
			"code": "compliance_gate_denied",
			"msg":  "request denied by compliance gate",
		},
	})
	header.Set("Content-Type", "application/json; charset=utf-8")
	header.Set("Content-Length", strconv.Itoa(len(body)))
	w.WriteHeader(http.StatusServiceUnavailable)
	_, _ = w.Write(body)
}

// readRequestBody returns the raw request body and rewinds it for the downstream
// relay handler. Fails closed (ok=false) if the body cannot be read.
func readRequestBody(c *gin.Context) (raw []byte, ok bool) {
	seeker, err := common.GetRequestBody(c)
	if err != nil {
		return nil, false
	}
	reader, isReader := seeker.(io.Reader)
	if !isReader {
		return nil, false
	}
	if _, err := seeker.Seek(0, io.SeekStart); err != nil {
		return nil, false
	}
	raw, err = io.ReadAll(reader)
	if err != nil {
		return nil, false
	}
	// rewind so the base relay can read the body again
	_, _ = seeker.Seek(0, io.SeekStart)
	return raw, true
}

func extractPromptText(rawBody []byte) string {
	fallback := string(rawBody)
	var parsed map[string]any
	if common.Unmarshal(rawBody, &parsed) != nil {
		return fallback
	}
	messages, ok := parsed["messages"].([]any)
	if !ok || len(messages) == 0 {
		return fallback
	}
	parts := make([]string, 0, len(messages))
	for _, item := range messages {
		message, ok := item.(map[string]any)
		if !ok {
			continue
		}
		appendChatContent(&parts, message["content"])
	}
	if len(parts) == 0 {
		return fallback
	}
	return strings.Join(parts, "\n")
}

func appendChatContent(parts *[]string, content any) {
	switch value := content.(type) {
	case string:
		if value != "" {
			*parts = append(*parts, value)
		}
	case []any:
		for _, item := range value {
			appendChatContent(parts, item)
		}
	case map[string]any:
		if text, _ := value["text"].(string); text != "" {
			*parts = append(*parts, text)
			return
		}
		if text, _ := value["input_text"].(string); text != "" {
			*parts = append(*parts, text)
			return
		}
		appendChatContent(parts, value["content"])
	}
}

// rewriteDesensitizedBody returns the request body with its prompt content
// replaced by the desensitize service's redacted text, so the base relay sends a
// PHI-free prompt upstream (the §D.1 red line: raw PHI must NEVER egress). When
// the redacted text splits 1:1 with the string messages, message roles/structure
// are preserved; otherwise it fails safe to a single redacted user message.
func rewriteDesensitizedBody(rawBody []byte, desensitizedText string) []byte {
	var parsed map[string]any
	if common.Unmarshal(rawBody, &parsed) != nil {
		return nil
	}
	messages, ok := parsed["messages"].([]any)
	if !ok || len(messages) == 0 {
		return nil
	}
	stringMsgs := make([]map[string]any, 0, len(messages))
	for _, item := range messages {
		if m, ok := item.(map[string]any); ok {
			if _, isStr := m["content"].(string); isStr {
				stringMsgs = append(stringMsgs, m)
			}
		}
	}
	if parts := strings.Split(desensitizedText, "\n"); len(stringMsgs) > 0 && len(stringMsgs) == len(parts) {
		for i, m := range stringMsgs {
			m["content"] = parts[i]
		}
	} else {
		parsed["messages"] = []any{map[string]any{"role": "user", "content": desensitizedText}}
	}
	newBody, err := common.Marshal(parsed)
	if err != nil {
		return nil
	}
	return newBody
}

func normalizeDataLevel(value any) (string, bool) {
	level, ok := value.(string)
	if !ok {
		return "", false
	}
	switch strings.ToUpper(strings.TrimSpace(level)) {
	case "L1", "1":
		return "L1", true
	case "L2", "2":
		return "L2", true
	case "L3", "3":
		return "L3", true
	case "L4", "4":
		return "L4", true
	default:
		return "", false
	}
}

func dataLevelRank(level string) int {
	switch level {
	case "L4":
		return 4
	case "L3":
		return 3
	case "L2":
		return 2
	case "L1":
		return 1
	default:
		return 0
	}
}

func higherDataLevel(current, candidate string) string {
	if dataLevelRank(candidate) > dataLevelRank(current) {
		return candidate
	}
	return current
}

func entityDataLevel(entity string) string {
	normalized := strings.ToUpper(strings.ReplaceAll(entity, "-", "_"))
	switch {
	case strings.Contains(normalized, "MRN"),
		strings.Contains(normalized, "MEDICAL_RECORD"),
		strings.Contains(normalized, "PATIENT_ID"),
		strings.Contains(normalized, "ID_CARD"),
		strings.Contains(normalized, "ID_NUMBER"),
		strings.Contains(normalized, "NATIONAL_ID"),
		strings.Contains(normalized, "SSN"),
		strings.Contains(normalized, "SOCIAL_SECURITY"),
		strings.Contains(normalized, "PASSPORT"),
		strings.Contains(normalized, "DRIVER_LICENSE"),
		strings.Contains(normalized, "INSURANCE"),
		strings.Contains(normalized, "BIOMETRIC"),
		strings.Contains(normalized, "GENETIC"),
		strings.Contains(normalized, "DNA"),
		strings.Contains(normalized, "FINGERPRINT"):
		return "L4"
	case strings.Contains(normalized, "NAME"),
		strings.Contains(normalized, "DIAGNOSIS"),
		strings.Contains(normalized, "DISEASE"),
		strings.Contains(normalized, "ICD"),
		strings.Contains(normalized, "MEDICATION"),
		strings.Contains(normalized, "DRUG"),
		strings.Contains(normalized, "PROCEDURE"),
		strings.Contains(normalized, "TREATMENT"),
		strings.Contains(normalized, "LAB"),
		strings.Contains(normalized, "CLINICAL"),
		strings.Contains(normalized, "CONDITION"),
		strings.Contains(normalized, "SYMPTOM"),
		strings.Contains(normalized, "HOSPITAL"),
		strings.Contains(normalized, "ADMISSION"),
		strings.Contains(normalized, "DISCHARGE"):
		return "L3"
	case strings.Contains(normalized, "PHONE"),
		strings.Contains(normalized, "EMAIL"),
		strings.Contains(normalized, "ADDRESS"),
		strings.Contains(normalized, "DATE"),
		strings.Contains(normalized, "DOB"),
		strings.Contains(normalized, "AGE"),
		strings.Contains(normalized, "ZIP"),
		strings.Contains(normalized, "LOCATION"),
		strings.Contains(normalized, "IP_ADDRESS"):
		return "L2"
	default:
		return "L2"
	}
}

func phiDataLevel(phi map[string]any) string {
	if phi == nil {
		return "L2"
	}
	level := "L1"
	hasEvidence := false
	for _, key := range []string{"data_level", "level", "phi_level", "max_data_level"} {
		if candidate, ok := normalizeDataLevel(phi[key]); ok {
			level = higherDataLevel(level, candidate)
			hasEvidence = true
		}
	}
	for _, key := range []string{"summary", "stats"} {
		nested, _ := phi[key].(map[string]any)
		for _, levelKey := range []string{"data_level", "level", "phi_level", "max_data_level"} {
			if candidate, ok := normalizeDataLevel(nested[levelKey]); ok {
				level = higherDataLevel(level, candidate)
				hasEvidence = true
			}
		}
	}
	if spans, _ := phi["spans"].([]any); len(spans) > 0 {
		hasEvidence = true
		for _, item := range spans {
			span, _ := item.(map[string]any)
			spanLevel := ""
			for _, key := range []string{"data_level", "level", "phi_level"} {
				if candidate, ok := normalizeDataLevel(span[key]); ok {
					spanLevel = candidate
					break
				}
			}
			if spanLevel == "" {
				entity, _ := span["entity_type"].(string)
				if entity == "" {
					entity, _ = span["type"].(string)
				}
				if entity != "" {
					spanLevel = entityDataLevel(entity)
				}
			}
			if spanLevel == "" {
				spanLevel = "L2"
			}
			level = higherDataLevel(level, spanLevel)
		}
	}
	if !hasEvidence {
		return "L2"
	}
	return level
}

func desensitizedFromResponse(desens map[string]any) bool {
	if desens == nil {
		return false
	}
	if value, ok := desens["desensitized"].(bool); ok {
		return value
	}
	if value, ok := desens["desensitized"].(string); ok {
		switch strings.ToLower(strings.TrimSpace(value)) {
		case "true", "1", "yes":
			return true
		case "false", "0", "no":
			return false
		}
	}
	for _, key := range []string{"desensitized_text", "map_ref", "map_id"} {
		if value, _ := desens[key].(string); value != "" {
			return true
		}
	}
	return false
}

func mapIDFromResponse(desens map[string]any, fallback string, desensitized bool) string {
	if desens != nil {
		if mapID, _ := desens["map_id"].(string); mapID != "" {
			return mapID
		}
		if context, _ := desens["context"].(map[string]any); context != nil {
			if mapID, _ := context["map_id"].(string); mapID != "" {
				return mapID
			}
		}
	}
	if desensitized {
		return fallback
	}
	return ""
}

func hasDetectorZeroHits(phi map[string]any) bool {
	summary, _ := phi["summary"].(map[string]any)
	if summary == nil {
		return false
	}
	switch value := summary["total_hits"].(type) {
	case float64:
		return value == 0
	case int:
		return value == 0
	}
	return false
}

func hasSensitivePHISignal(phi map[string]any) bool {
	spans, _ := phi["spans"].([]any)
	for _, item := range spans {
		span, _ := item.(map[string]any)
		entity, _ := span["entity_type"].(string)
		if entity == "" {
			entity, _ = span["type"].(string)
		}
		normalized := strings.ToUpper(strings.ReplaceAll(entity, "-", "_"))
		if strings.Contains(normalized, "NAME") ||
			strings.Contains(normalized, "MRN") ||
			strings.Contains(normalized, "DIAGNOSIS") ||
			strings.Contains(normalized, "DISEASE") ||
			strings.Contains(normalized, "ICD") ||
			strings.Contains(normalized, "MEDICATION") ||
			strings.Contains(normalized, "DRUG") ||
			strings.Contains(normalized, "PROCEDURE") ||
			strings.Contains(normalized, "TREATMENT") ||
			strings.Contains(normalized, "LAB") ||
			strings.Contains(normalized, "CLINICAL") ||
			strings.Contains(normalized, "CONDITION") ||
			strings.Contains(normalized, "SYMPTOM") {
			return true
		}
	}
	return false
}

func hasLowSensitivityEvidence(phi map[string]any, dataLevel string) bool {
	if dataLevelRank(dataLevel) > dataLevelRank("L2") {
		return false
	}
	if level, ok := normalizeDataLevel(phi["low_sensitivity_evidence"]); ok {
		return dataLevelRank(level) <= dataLevelRank("L2")
	}
	if value, ok := phi["low_sensitivity_evidence"].(bool); ok {
		return value
	}
	if value, ok := phi["clean"].(bool); ok {
		return value
	}
	for _, key := range []string{"data_level", "level", "phi_level", "max_data_level"} {
		if _, ok := normalizeDataLevel(phi[key]); ok {
			return true
		}
	}
	spans, _ := phi["spans"].([]any)
	return len(spans) > 0 && !hasDetectorZeroHits(phi)
}

func optionBLane(phi map[string]any, dataLevel, mapID string, desensitized bool) string {
	if !desensitized || mapID == "" {
		return "sensitive"
	}
	if dataLevelRank(dataLevel) >= dataLevelRank("L3") || hasSensitivePHISignal(phi) {
		return "sensitive"
	}
	if hasLowSensitivityEvidence(phi, dataLevel) {
		return "normal"
	}
	return "sensitive"
}

func newComplianceMapID() string {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err == nil {
		return "mh_" + hex.EncodeToString(raw[:])
	}
	return "mh_" + strconv.FormatInt(time.Now().UnixNano(), 36)
}

type bufferedComplianceWriter struct {
	gin.ResponseWriter
	body        bytes.Buffer
	status      int
	size        int
	wroteHeader bool
}

func newBufferedComplianceWriter(w gin.ResponseWriter) *bufferedComplianceWriter {
	return &bufferedComplianceWriter{
		ResponseWriter: w,
		status:         http.StatusOK,
		size:           -1,
	}
}

func (w *bufferedComplianceWriter) WriteHeader(code int) {
	if w.wroteHeader {
		return
	}
	w.status = code
	w.wroteHeader = true
}

func (w *bufferedComplianceWriter) WriteHeaderNow() {
	if !w.wroteHeader {
		w.WriteHeader(w.status)
	}
}

func (w *bufferedComplianceWriter) Write(data []byte) (int, error) {
	w.WriteHeaderNow()
	n, err := w.body.Write(data)
	if n > 0 {
		if w.size < 0 {
			w.size = 0
		}
		w.size += n
	}
	return n, err
}

func (w *bufferedComplianceWriter) WriteString(data string) (int, error) {
	return w.Write([]byte(data))
}

// Flush must be a no-op: the gate has to HOLD the whole buffered response until
// post-call outbound-safety decides. Without this override, a relay handler that
// calls Flush() flushes the EMBEDDED original writer (committing the relay's
// Content-Length), so a later outbound-block 503 ships a stale Content-Length and
// the client gets a truncated/IncompleteRead response.
func (w *bufferedComplianceWriter) Flush() {}

func (w *bufferedComplianceWriter) Status() int {
	return w.status
}

func (w *bufferedComplianceWriter) Size() int {
	return w.size
}

func (w *bufferedComplianceWriter) Written() bool {
	return w.wroteHeader
}

func writeBufferedResponse(dst gin.ResponseWriter, src *bufferedComplianceWriter) {
	dst.WriteHeader(src.status)
	if src.body.Len() > 0 {
		_, _ = dst.Write(src.body.Bytes())
	}
}

// tierFromRequest derives the gate-attested tier. The gate determines these
// fields (never the caller).
func tierFromRequest(c *gin.Context, rawBody []byte, phi, desens map[string]any) map[string]string {
	model := ""
	var parsed map[string]any
	if common.Unmarshal(rawBody, &parsed) == nil {
		if m, _ := parsed["model"].(string); m != "" {
			model = m
		}
	}
	return map[string]string{
		"model_id":             model,
		"agent_role":           c.GetHeader("X-MedHarness-Agent-Role"),
		"data_level":           phiDataLevel(phi),
		"change_id":            c.GetHeader("X-MedHarness-Change-Id"),
		"caller_vendor_family": c.GetHeader("X-MedHarness-Caller-Vendor-Family"),
		"desensitized":         strconv.FormatBool(desensitizedFromResponse(desens)),
	}
}

// MedHarnessCompliance welds the §D.1 pre-call gate onto /v1/*.
// stampAllowedModelSet records the policy-vetted allowed_model_set from the
// RouteDecision onto the request context so the base relay can fail closed if a
// channel's model_mapping redirects the effective upstream model outside it
// (§D.1 "base has no autonomy", BE-7.3). A missing/empty set is a no-op, so
// non-MedHarness deployments and decisions without a set are unaffected.
func stampAllowedModelSet(c *gin.Context, body map[string]any) {
	if body == nil {
		return
	}
	raw, ok := body["allowed_model_set"].([]any)
	if !ok || len(raw) == 0 {
		return
	}
	set := make(map[string]bool, len(raw))
	for _, item := range raw {
		if name, ok := item.(string); ok && name != "" {
			set[name] = true
		}
	}
	if len(set) > 0 {
		c.Set(string(constant.ContextKeyMedHarnessAllowedModelSet), set)
	}
}

func MedHarnessCompliance() gin.HandlerFunc {
	phiURL := complianceEnv("PHI_DETECTOR_URL", "http://phi-detector:9000") + "/scan"
	desensURL := complianceEnv("DESENSITIZE_URL", "http://desensitize:9000") + "/encrypt"
	routerURL := complianceEnv("MODEL_ROUTER_URL", "http://model-router:9000") + "/route"
	injectionURL := complianceEnv("INJECTION_URL", "http://prompt-injection-scan:9000") + "/scan"
	outboundURL := complianceEnv("OUTBOUND_SAFETY_URL", "http://outbound-safety:9000") + "/scan"
	secret := []byte(os.Getenv("MODEL_ROUTER_TIER_SECRET"))
	client := &http.Client{Timeout: complianceGateTimeout}

	return func(c *gin.Context) {
		rawBody, ok := readRequestBody(c)
		if !ok {
			abortCompliance(c)
			return
		}

		promptText := extractPromptText(rawBody)
		scanPayload, err := common.Marshal(map[string]string{"text": promptText})
		if err != nil {
			abortCompliance(c)
			return
		}

		// §D.1 pre-call order — fail-closed at every step.
		// 1. phi-detect
		phi := callComplianceGate(client, phiURL, scanPayload)
		if !phi.ok || phi.denied {
			abortCompliance(c)
			return
		}
		// 2. desensitize (envelope -> map_id)
		requestMapID := newComplianceMapID()
		desensPayload, err := common.Marshal(map[string]any{
			"text":      promptText,
			"phi_spans": phi.body["spans"],
			"context": map[string]any{
				"change_id": c.GetHeader("X-MedHarness-Change-Id"),
				"map_id":    requestMapID,
			},
		})
		if err != nil {
			abortCompliance(c)
			return
		}
		desens := callComplianceGate(client, desensURL, desensPayload)
		if !desens.ok || desens.denied {
			abortCompliance(c)
			return
		}
		desensitized := desensitizedFromResponse(desens.body)
		mapID := mapIDFromResponse(desens.body, requestMapID, desensitized)

		// §D.1 red line: the upstream must NEVER receive raw PHI. desensitize
		// returns the redacted prompt; rewrite the relayed body with it so the
		// base relay sends the desensitized prompt (not the original).
		if dtext, _ := desens.body["desensitized_text"].(string); dtext != "" {
			if newBody := rewriteDesensitizedBody(rawBody, dtext); newBody != nil {
				if storage, err := common.CreateBodyStorage(newBody); err == nil {
					c.Set(common.KeyBodyStorage, storage)
					c.Request.ContentLength = int64(len(newBody))
					c.Request.Header.Set("Content-Length", strconv.Itoa(len(newBody)))
				}
			}
		}

		// 3. sign the gate-attested tier (B1)
		tier := tierFromRequest(c, rawBody, phi.body, desens.body)
		tierSig := signTier(tier, secret)
		lane := optionBLane(phi.body, tier["data_level"], mapID, desensitized)

		// 4. model-router (verifies tier_sig, returns a signed RouteDecision)
		routePayload, _ := common.Marshal(map[string]any{
			"model_id":             tier["model_id"],
			"agent_role":           tier["agent_role"],
			"data_level":           tier["data_level"],
			"change_id":            tier["change_id"],
			"caller_vendor_family": tier["caller_vendor_family"],
			"desensitized":         desensitized,
			"lane":                 lane,
			"map_id":               mapID,
			"tier_sig":             tierSig,
		})
		route := callComplianceGate(client, routerURL, routePayload)
		if !route.ok || route.denied {
			abortCompliance(c)
			return
		}
		// BE-7.3: stamp the policy-vetted allowed_model_set so the base relay can
		// enforce "base has no autonomy" — a channel's model_mapping must not
		// redirect the effective upstream model outside this set
		// (see relay/helper/model_mapped.go).
		stampAllowedModelSet(c, route.body)
		// 5. injection
		if r := callComplianceGate(client, injectionURL, scanPayload); !r.ok || r.denied {
			abortCompliance(c)
			return
		}

		// all pre-call gates passed -> base relay, then post-call outbound safety
		originalWriter := c.Writer
		bufferedWriter := newBufferedComplianceWriter(originalWriter)
		c.Writer = bufferedWriter
		c.Next()
		c.Writer = originalWriter

		outboundPayload, err := common.Marshal(map[string]any{
			"text": bufferedWriter.body.String(),
			"context": map[string]any{
				"lane":       lane,
				"data_level": tier["data_level"],
				"map_id":     mapID,
			},
		})
		if err != nil {
			writeGenericCompliance503(originalWriter)
			c.Abort()
			return
		}
		if r := callComplianceGate(client, outboundURL, outboundPayload); !r.ok || r.denied {
			writeGenericCompliance503(originalWriter)
			c.Abort()
			return
		}
		writeBufferedResponse(originalWriter, bufferedWriter)
	}
}
