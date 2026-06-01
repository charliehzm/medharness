package middleware

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

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

func newGateServer(name string, order *[]string, mu *sync.Mutex, deny bool) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		mu.Lock()
		*order = append(*order, name)
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		if deny {
			_, _ = w.Write([]byte(`{"decision":"deny"}`))
			return
		}
		_, _ = w.Write([]byte(`{"decision":"allow","map_id":"map-x"}`))
	}))
}

func runComplianceRequest(t *testing.T, phiDeny bool) (status int, nextCalled bool, order []string) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	var mu sync.Mutex
	phi := newGateServer("phi", &order, &mu, phiDeny)
	defer phi.Close()
	desens := newGateServer("desens", &order, &mu, false)
	defer desens.Close()
	router := newGateServer("router", &order, &mu, false)
	defer router.Close()
	injection := newGateServer("injection", &order, &mu, false)
	defer injection.Close()

	t.Setenv("PHI_DETECTOR_URL", phi.URL)
	t.Setenv("DESENSITIZE_URL", desens.URL)
	t.Setenv("MODEL_ROUTER_URL", router.URL)
	t.Setenv("INJECTION_URL", injection.URL)
	t.Setenv("MODEL_ROUTER_TIER_SECRET", "medharness-test-secret")

	// Env is read at handler construction, so build AFTER Setenv.
	engine := gin.New()
	engine.POST("/v1/chat/completions", MedHarnessCompliance(), func(c *gin.Context) {
		nextCalled = true
		c.Status(http.StatusOK)
	})

	w := httptest.NewRecorder()
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/chat/completions",
		strings.NewReader(`{"model":"qwen-max","messages":[{"role":"user","content":"hi"}]}`),
	)
	req.Header.Set("Content-Type", "application/json")
	engine.ServeHTTP(w, req)
	return w.Code, nextCalled, order
}

// TestComplianceHappyPath: all gates pass -> §D.1 order phi->desens->router->injection -> base relay.
func TestComplianceHappyPath(t *testing.T) {
	status, nextCalled, order := runComplianceRequest(t, false)
	if !nextCalled {
		t.Fatalf("base relay (c.Next) was not reached on the happy path")
	}
	if status != http.StatusOK {
		t.Fatalf("status = %d, want 200", status)
	}
	if got := strings.Join(order, ","); got != "phi,desens,router,injection" {
		t.Fatalf("gate order = %q, want phi,desens,router,injection", got)
	}
}

// TestComplianceFailClosed: a gate deny aborts the request and never reaches base relay.
func TestComplianceFailClosed(t *testing.T) {
	status, nextCalled, order := runComplianceRequest(t, true)
	if nextCalled {
		t.Fatalf("fail-closed violated: base relay was reached after a gate deny")
	}
	if status != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", status)
	}
	if len(order) != 1 || order[0] != "phi" {
		t.Fatalf("after deny the chain must stop; calls = %v, want [phi]", order)
	}
}
