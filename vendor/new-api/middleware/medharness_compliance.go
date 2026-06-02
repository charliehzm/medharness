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
// TODO(BE-7.2): post-call outbound-safety /scan on the response; Option B lane
// (clean lane needs positive low-sensitivity evidence; name/MRN/clinical signal
// /L3+ default to the sensitive lane); enforce that the base layer only fans out
// within RouteDecision.allowed_model_set; precise message-text extraction.

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/QuantumNous/new-api/common"
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
		if decision, _ := parsed["decision"].(string); decision == "deny" {
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

// tierFromRequest derives the gate-attested tier. The gate determines these
// fields (never the caller). For BE-7.1 the data_level is a conservative default
// after desensitization; precise derivation is TODO(BE-7.2).
func tierFromRequest(c *gin.Context, rawBody []byte) map[string]string {
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
		"data_level":           "L2",
		"change_id":            c.GetHeader("X-MedHarness-Change-Id"),
		"caller_vendor_family": "",
		"desensitized":         "true",
	}
}

// MedHarnessCompliance welds the §D.1 pre-call gate onto /v1/*.
func MedHarnessCompliance() gin.HandlerFunc {
	phiURL := complianceEnv("PHI_DETECTOR_URL", "http://phi-detector:9000") + "/scan"
	desensURL := complianceEnv("DESENSITIZE_URL", "http://desensitize:9000") + "/encrypt"
	routerURL := complianceEnv("MODEL_ROUTER_URL", "http://model-router:9000") + "/route"
	injectionURL := complianceEnv("INJECTION_URL", "http://prompt-injection-scan:9000") + "/scan"
	secret := []byte(os.Getenv("MODEL_ROUTER_TIER_SECRET"))
	client := &http.Client{Timeout: complianceGateTimeout}

	return func(c *gin.Context) {
		rawBody, ok := readRequestBody(c)
		if !ok {
			abortCompliance(c)
			return
		}

		// The gate scans the whole request body for PHI / injection signals.
		scanPayload, _ := common.Marshal(map[string]string{"text": string(rawBody)})

		// §D.1 pre-call order — fail-closed at every step.
		// 1. phi-detect
		if r := callComplianceGate(client, phiURL, scanPayload); !r.ok || r.denied {
			abortCompliance(c)
			return
		}
		// 2. desensitize (envelope -> map_id)
		desens := callComplianceGate(client, desensURL, scanPayload)
		if !desens.ok || desens.denied {
			abortCompliance(c)
			return
		}
		mapID, _ := desens.body["map_id"].(string)

		// 3. sign the gate-attested tier (B1)
		tier := tierFromRequest(c, rawBody)
		tierSig := signTier(tier, secret)

		// 4. model-router (verifies tier_sig, returns a signed RouteDecision)
		routePayload, _ := common.Marshal(map[string]any{
			"model_id":             tier["model_id"],
			"agent_role":           tier["agent_role"],
			"data_level":           tier["data_level"],
			"change_id":            tier["change_id"],
			"caller_vendor_family": tier["caller_vendor_family"],
			"desensitized":         true,
			"map_id":               mapID,
			"tier_sig":             tierSig,
		})
		if r := callComplianceGate(client, routerURL, routePayload); !r.ok || r.denied {
			abortCompliance(c)
			return
		}
		// 5. injection
		if r := callComplianceGate(client, injectionURL, scanPayload); !r.ok || r.denied {
			abortCompliance(c)
			return
		}

		// all pre-call gates passed -> base relay
		c.Next()
	}
}
