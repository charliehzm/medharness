package middleware

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/constant"
	"github.com/gin-gonic/gin"
)

// TestSignTierMatchesPython locks cross-language HMAC compatibility: the Go gate
// signer MUST produce the exact bytes that mcp/model-router/tier_trust.py
// verifies (B1). The expected value is computed by tier_trust.sign_tier with the
// same fixed input + secret.
func TestSignTierMatchesPython(t *testing.T) {
	tier := map[string]string{
		"model_id":             "qwen-max",
		"agent_role":           "coder",
		"data_level":           "L2",
		"change_id":            "c1",
		"caller_vendor_family": "alibaba",
		"desensitized":         "true",
	}
	const want = "e930e1518f71ccd98e630f1c6ee67c048287610b78f947a3e627f1540889f3f8"
	if got := signTier(tier, []byte("medharness-test-secret")); got != want {
		t.Fatalf("signTier incompatible with Python tier_trust.sign_tier:\n got  %s\n want %s", got, want)
	}
}

type gateTestConfig struct {
	phiResponse       string
	desensResponse    string
	routerResponse    string
	injectionResponse string
	outboundResponse  string
	requestBody       string
	baseStatus        int
	baseBody          string
}

type gateTestResult struct {
	status       int
	body         string
	nextCalled   bool
	order        []string
	captures     map[string]map[string]any
	allowedStamp map[string]bool
}

func defaultGateTestConfig() gateTestConfig {
	return gateTestConfig{
		phiResponse:       `{"data_level":"L2","spans":[],"summary":{"total_hits":0}}`,
		desensResponse:    `{"desensitized":true,"map_id":"map-x","desensitized_text":"hi","map_ref":"ref-x"}`,
		routerResponse:    `{"decision":"allow"}`,
		injectionResponse: `{"decision":"allow"}`,
		outboundResponse:  `{"decision":"allow"}`,
		requestBody:       `{"model":"qwen-max","messages":[{"role":"user","content":"hi"}]}`,
		baseStatus:        http.StatusOK,
	}
}

type gateRoundTripper struct {
	order     *[]string
	mu        *sync.Mutex
	responses map[string]string
	captures  map[string]map[string]any
}

func (rt gateRoundTripper) RoundTrip(r *http.Request) (*http.Response, error) {
	raw, _ := io.ReadAll(r.Body)
	var parsed map[string]any
	_ = common.Unmarshal(raw, &parsed)
	name := strings.TrimSuffix(r.URL.Host, ".test")
	rt.mu.Lock()
	*rt.order = append(*rt.order, name)
	if rt.captures != nil {
		rt.captures[name] = parsed
	}
	rt.mu.Unlock()

	body := []byte(rt.responses[name])
	return &http.Response{
		StatusCode:    http.StatusOK,
		Status:        "200 OK",
		Header:        http.Header{"Content-Type": []string{"application/json"}},
		Body:          io.NopCloser(bytes.NewReader(body)),
		ContentLength: int64(len(body)),
		Request:       r,
	}, nil
}

func runComplianceRequest(t *testing.T, overrides gateTestConfig) gateTestResult {
	t.Helper()
	gin.SetMode(gin.TestMode)

	cfg := defaultGateTestConfig()
	if overrides.phiResponse != "" {
		cfg.phiResponse = overrides.phiResponse
	}
	if overrides.desensResponse != "" {
		cfg.desensResponse = overrides.desensResponse
	}
	if overrides.routerResponse != "" {
		cfg.routerResponse = overrides.routerResponse
	}
	if overrides.injectionResponse != "" {
		cfg.injectionResponse = overrides.injectionResponse
	}
	if overrides.outboundResponse != "" {
		cfg.outboundResponse = overrides.outboundResponse
	}
	if overrides.requestBody != "" {
		cfg.requestBody = overrides.requestBody
	}
	if overrides.baseStatus != 0 {
		cfg.baseStatus = overrides.baseStatus
	}
	cfg.baseBody = overrides.baseBody

	var mu sync.Mutex
	var order []string
	captures := map[string]map[string]any{}
	oldTransport := http.DefaultTransport
	http.DefaultTransport = gateRoundTripper{
		order: &order,
		mu:    &mu,
		responses: map[string]string{
			"phi":       cfg.phiResponse,
			"desens":    cfg.desensResponse,
			"router":    cfg.routerResponse,
			"injection": cfg.injectionResponse,
			"outbound":  cfg.outboundResponse,
		},
		captures: captures,
	}
	t.Cleanup(func() {
		http.DefaultTransport = oldTransport
	})

	t.Setenv("PHI_DETECTOR_URL", "http://phi.test")
	t.Setenv("DESENSITIZE_URL", "http://desens.test")
	t.Setenv("MODEL_ROUTER_URL", "http://router.test")
	t.Setenv("INJECTION_URL", "http://injection.test")
	t.Setenv("OUTBOUND_SAFETY_URL", "http://outbound.test")
	t.Setenv("MODEL_ROUTER_TIER_SECRET", "medharness-test-secret")

	// Env is read at handler construction, so build AFTER Setenv.
	engine := gin.New()
	nextCalled := false
	var allowedStamp map[string]bool
	engine.POST("/v1/chat/completions", MedHarnessCompliance(), func(c *gin.Context) {
		nextCalled = true
		if v, ok := c.Get(string(constant.ContextKeyMedHarnessAllowedModelSet)); ok {
			if set, ok := v.(map[string]bool); ok {
				allowedStamp = set
			}
		}
		c.Status(cfg.baseStatus)
		if cfg.baseBody != "" {
			_, _ = c.Writer.Write([]byte(cfg.baseBody))
		}
	})

	w := httptest.NewRecorder()
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/chat/completions",
		strings.NewReader(cfg.requestBody),
	)
	req.Header.Set("Content-Type", "application/json")
	engine.ServeHTTP(w, req)
	return gateTestResult{
		status:       w.Code,
		body:         w.Body.String(),
		nextCalled:   nextCalled,
		order:        order,
		captures:     captures,
		allowedStamp: allowedStamp,
	}
}

// TestComplianceHappyPath: all gates pass -> §D.1 order phi->desens->router->injection -> base relay.
func TestComplianceHappyPath(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{})
	if !result.nextCalled {
		t.Fatalf("base relay (c.Next) was not reached on the happy path")
	}
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if got := strings.Join(result.order, ","); got != "phi,desens,router,injection,outbound" {
		t.Fatalf("gate order = %q, want phi,desens,router,injection,outbound", got)
	}
	if got, _ := result.captures["phi"]["text"].(string); got != "hi" {
		t.Fatalf("phi text = %q, want extracted chat message text", got)
	}
}

// TestComplianceFailClosed: a gate deny aborts the request and never reaches base relay.
func TestComplianceFailClosed(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{phiResponse: `{"decision":"deny"}`})
	if result.nextCalled {
		t.Fatalf("fail-closed violated: base relay was reached after a gate deny")
	}
	if result.status != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", result.status)
	}
	if len(result.order) != 1 || result.order[0] != "phi" {
		t.Fatalf("after deny the chain must stop; calls = %v, want [phi]", result.order)
	}
}

// TestComplianceStampsAllowedModelSet verifies the RouteDecision.allowed_model_set
// is stamped onto the request context (BE-7.3) so the base relay can fence a
// channel's model_mapping to the policy-vetted set.
func TestComplianceStampsAllowedModelSet(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{
		routerResponse: `{"decision":"allow","allowed_model_set":["qwen-max","qwen-plus"]}`,
	})
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if !result.nextCalled {
		t.Fatalf("base relay must run so the stamp is observable")
	}
	if result.allowedStamp == nil {
		t.Fatalf("allowed_model_set was not stamped on the context")
	}
	if len(result.allowedStamp) != 2 || !result.allowedStamp["qwen-max"] || !result.allowedStamp["qwen-plus"] {
		t.Fatalf("stamped set = %v, want {qwen-max, qwen-plus}", result.allowedStamp)
	}
}

// TestComplianceNoAllowedSetLeavesContextUnstamped: when the router omits the
// set, nothing is stamped (the base relay then keeps upstream default behavior).
func TestComplianceNoAllowedSetLeavesContextUnstamped(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{routerResponse: `{"decision":"allow"}`})
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if result.allowedStamp != nil {
		t.Fatalf("no allowed_model_set in decision must leave context unstamped, got %v", result.allowedStamp)
	}
}

// TestDenyZeroProviderConnection is the ADR-18 §5 acceptance: a model-router
// deny MUST halt the spine before base relay, so the upstream provider sees
// ZERO connections (no egress, no cache write, no upstream log on deny). The
// base handler stands in for "connect to provider"; it must never run.
func TestDenyZeroProviderConnection(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{routerResponse: `{"decision":"deny"}`})
	if result.nextCalled {
		t.Fatalf("deny→provider must be 0 connections: base relay ran after model-router deny")
	}
	if result.status != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", result.status)
	}
	if got := strings.Join(result.order, ","); got != "phi,desens,router" {
		t.Fatalf("router deny must stop the chain at router (no injection/base/outbound); calls = %q, want phi,desens,router", got)
	}
}

func TestComplianceTierUsesHighestPHILevel(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{
		phiResponse: `{"spans":[{"entity_type":"MRN","data_level":"L4","start":0,"end":3,"score":0.99}],"summary":{"total_hits":1}}`,
	})
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if got, _ := result.captures["router"]["data_level"].(string); got != "L4" {
		t.Fatalf("router data_level = %q, want L4", got)
	}
}

func TestComplianceOptionBLaneNameDefaultsSensitive(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{
		requestBody: `{"model":"qwen-max","messages":[{"role":"user","content":"patient name: synthetic alice"}]}`,
		phiResponse: `{"spans":[{"entity_type":"PERSON_NAME","start":14,"end":29,"score":0.95}],"summary":{"total_hits":1}}`,
	})
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if got, _ := result.captures["router"]["lane"].(string); got != "sensitive" {
		t.Fatalf("router lane = %q, want sensitive", got)
	}
}

func TestComplianceOutboundDenyReplacesResponse(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{
		baseBody:         `{"choices":[{"message":{"content":"upstream body"}}]}`,
		outboundResponse: `{"decision":"deny"}`,
	})
	if !result.nextCalled {
		t.Fatalf("base relay should be reached before post-call outbound safety")
	}
	if result.status != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", result.status)
	}
	if strings.Contains(result.body, "upstream body") {
		t.Fatalf("outbound deny leaked buffered upstream body: %s", result.body)
	}
	if got := strings.Join(result.order, ","); got != "phi,desens,router,injection,outbound" {
		t.Fatalf("gate order = %q, want phi,desens,router,injection,outbound", got)
	}
}

// --- Fix#1: embeddings `input` desensitization (the §D.1 red-line bypass) -------

const embRawID = "110101199001011237" // SYNTHETIC valid-checksum CN-ID

// extractPromptText must read embeddings `input` (string OR array) — not just
// `messages` — so phi-detect/desensitize see the PHI; chat bodies still work.
func TestExtractPromptTextEmbeddingsInput(t *testing.T) {
	cases := []struct{ name, body, want string }{
		{"string input", `{"model":"m","input":"id ` + embRawID + `"}`, "id " + embRawID},
		{"array input", `{"model":"m","input":["id ` + embRawID + `","note"]}`, "id " + embRawID + "\nnote"},
		{"chat regression", `{"model":"m","messages":[{"role":"user","content":"hi"}]}`, "hi"},
		{"neither -> raw fallback", `{"model":"m"}`, `{"model":"m"}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := extractPromptText([]byte(tc.body)); got != tc.want {
				t.Fatalf("extractPromptText = %q, want %q", got, tc.want)
			}
		})
	}
}

// rewriteDesensitizedBody must rewrite embeddings `input` with the redacted text so
// the upstream never receives the raw identifier — string and array shapes — while
// still rewriting chat `messages`.
func TestRewriteDesensitizedBodyEmbeddingsInput(t *testing.T) {
	t.Run("string input rewritten", func(t *testing.T) {
		out := rewriteDesensitizedBody([]byte(`{"model":"m","input":"id `+embRawID+`"}`), "id PHI_CN_ID_x")
		if out == nil || strings.Contains(string(out), embRawID) {
			t.Fatalf("raw id survived string rewrite: %s", out)
		}
		var parsed map[string]any
		_ = common.Unmarshal(out, &parsed)
		if got, _ := parsed["input"].(string); got != "id PHI_CN_ID_x" {
			t.Fatalf("input = %q, want desensitized string", got)
		}
	})
	t.Run("array input element-wise (1:1 split)", func(t *testing.T) {
		out := rewriteDesensitizedBody([]byte(`{"model":"m","input":["id `+embRawID+`","note"]}`), "id PHI_CN_ID_x\nnote")
		if out == nil || strings.Contains(string(out), embRawID) {
			t.Fatalf("raw id survived array rewrite: %s", out)
		}
		var parsed map[string]any
		_ = common.Unmarshal(out, &parsed)
		arr, ok := parsed["input"].([]any)
		if !ok || len(arr) != 2 || arr[0] != "id PHI_CN_ID_x" || arr[1] != "note" {
			t.Fatalf("array not rewritten 1:1: %v", parsed["input"])
		}
	})
	t.Run("array input safe-collapse (mismatched split)", func(t *testing.T) {
		out := rewriteDesensitizedBody([]byte(`{"model":"m","input":["id `+embRawID+`","a","b"]}`), "one blob")
		if out == nil || strings.Contains(string(out), embRawID) {
			t.Fatalf("raw id survived collapse: %s", out)
		}
	})
	t.Run("chat messages regression", func(t *testing.T) {
		out := rewriteDesensitizedBody([]byte(`{"model":"m","messages":[{"role":"user","content":"id `+embRawID+`"}]}`), "id PHI_CN_ID_x")
		if out == nil || strings.Contains(string(out), embRawID) {
			t.Fatalf("raw id survived chat rewrite: %s", out)
		}
	})
}

// End-to-end through the live middleware (in-process): an embeddings body's `input`
// text must reach the phi scan AND the base relay must receive the desensitized body.
func TestComplianceEmbeddingsInputDesensitized(t *testing.T) {
	result := runComplianceRequest(t, gateTestConfig{
		requestBody:    `{"model":"qwen-max","input":"patient id ` + embRawID + `"}`,
		desensResponse: `{"desensitized":true,"map_id":"map-x","desensitized_text":"patient id PHI_CN_ID_x","map_ref":"ref-x"}`,
	})
	if result.status != http.StatusOK {
		t.Fatalf("status = %d, want 200", result.status)
	}
	if got, _ := result.captures["phi"]["text"].(string); got != "patient id "+embRawID {
		t.Fatalf("phi scan text = %q, want the embeddings input text", got)
	}
}

// --- Fix#2: SSE reassembly for the streaming outbound-evasion case -------------

func TestReassembleSSEContent(t *testing.T) {
	// harmful phrase split across two delta.content frames must reassemble whole.
	split := "data: {\"choices\":[{\"delta\":{\"content\":\"make a \"}}]}\n\n" +
		"data: {\"choices\":[{\"delta\":{\"content\":\"bomb\"}}]}\n\n" +
		"data: [DONE]\n\n"
	if got := reassembleSSEContent(split); got != "make a bomb" {
		t.Fatalf("split reassembly = %q, want %q", got, "make a bomb")
	}
	// raw split frames do NOT contain the contiguous phrase (the evasion premise).
	if strings.Contains(split, "make a bomb") {
		t.Fatalf("test premise broken: raw frames already contain the contiguous phrase")
	}
	single := "data: {\"choices\":[{\"delta\":{\"content\":\"hello world\"}}]}\n\ndata: [DONE]\n\n"
	if got := reassembleSSEContent(single); got != "hello world" {
		t.Fatalf("single-frame reassembly = %q, want %q", got, "hello world")
	}
	// non-SSE (a plain JSON completion body) yields no reassembled text.
	if got := reassembleSSEContent(`{"choices":[{"message":{"content":"not sse"}}]}`); got != "" {
		t.Fatalf("non-SSE reassembly = %q, want empty", got)
	}
}
