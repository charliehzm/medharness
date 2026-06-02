package helper

import (
	"net/http/httptest"
	"testing"

	"github.com/QuantumNous/new-api/constant"
	relaycommon "github.com/QuantumNous/new-api/relay/common"
	"github.com/gin-gonic/gin"
)

// BE-7.3 §D.1 "base has no autonomy": ModelMappedHelper must fail closed when a
// channel's model_mapping redirects the effective upstream model outside the
// policy-vetted allowed_model_set stamped by middleware.MedHarnessCompliance,
// and stay a no-op when no set is stamped (non-MedHarness deployments).

func newMappedTestContext(t *testing.T, modelMapping string, allowed map[string]bool) *gin.Context {
	t.Helper()
	gin.SetMode(gin.TestMode)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	if modelMapping != "" {
		c.Set(string(constant.ContextKeyChannelModelMapping), modelMapping)
	}
	if allowed != nil {
		c.Set(string(constant.ContextKeyMedHarnessAllowedModelSet), allowed)
	}
	return c
}

func newMappedTestInfo(model string) *relaycommon.RelayInfo {
	return &relaycommon.RelayInfo{
		OriginModelName: model,
		ChannelMeta:     &relaycommon.ChannelMeta{UpstreamModelName: model},
	}
}

func TestModelMappedHelperAllowsInSetRedirect(t *testing.T) {
	c := newMappedTestContext(t, `{"qwen-max":"qwen-plus"}`, map[string]bool{"qwen-max": true, "qwen-plus": true})
	info := newMappedTestInfo("qwen-max")
	if err := ModelMappedHelper(c, info, nil); err != nil {
		t.Fatalf("in-set mapped model must pass, got %v", err)
	}
	if info.UpstreamModelName != "qwen-plus" {
		t.Fatalf("UpstreamModelName = %q, want qwen-plus", info.UpstreamModelName)
	}
}

func TestModelMappedHelperBlocksOutOfSetRedirect(t *testing.T) {
	c := newMappedTestContext(t, `{"qwen-max":"gpt-4o"}`, map[string]bool{"qwen-max": true})
	info := newMappedTestInfo("qwen-max")
	err := ModelMappedHelper(c, info, nil)
	if err == nil {
		t.Fatalf("a model_mapping that redirects outside allowed_model_set must fail closed")
	}
	if err.Error() != "medharness_model_outside_allowlist" {
		t.Fatalf("err = %q, want generic medharness_model_outside_allowlist", err.Error())
	}
}

func TestModelMappedHelperNoStampIsUnaffected(t *testing.T) {
	// No allowed_model_set stamped (non-MedHarness path): any redirect is allowed.
	c := newMappedTestContext(t, `{"qwen-max":"gpt-4o"}`, nil)
	info := newMappedTestInfo("qwen-max")
	if err := ModelMappedHelper(c, info, nil); err != nil {
		t.Fatalf("without a stamped set the guard must be a no-op, got %v", err)
	}
	if info.UpstreamModelName != "gpt-4o" {
		t.Fatalf("UpstreamModelName = %q, want gpt-4o", info.UpstreamModelName)
	}
}

func TestModelMappedHelperUnmappedVettedModelPasses(t *testing.T) {
	// No model_mapping; effective == origin == vetted model -> passes.
	c := newMappedTestContext(t, "", map[string]bool{"qwen-max": true})
	info := newMappedTestInfo("qwen-max")
	if err := ModelMappedHelper(c, info, nil); err != nil {
		t.Fatalf("unmapped vetted model must pass, got %v", err)
	}
}

func TestModelMappedHelperEmptySetIsNoOp(t *testing.T) {
	// An empty set must not block (defensive: treat as "not enforced").
	c := newMappedTestContext(t, `{"qwen-max":"gpt-4o"}`, map[string]bool{})
	info := newMappedTestInfo("qwen-max")
	if err := ModelMappedHelper(c, info, nil); err != nil {
		t.Fatalf("empty allowed_model_set must be a no-op, got %v", err)
	}
}
