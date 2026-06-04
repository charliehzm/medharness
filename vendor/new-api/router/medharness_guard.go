package router

import (
	"net/http"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/gin-gonic/gin"
)

var medHarnessBlockedPrefixes = []string{
	"/api/oauth",
	"/api/user/oauth",
	"/api/user/topup",
	"/api/subscription",
	"/api/redemption",
	"/api/stripe",
	"/api/creem",
	"/api/waffo",
	"/api/custom-oauth-provider",
	"/api/option/waffo-pancake",
	"/dashboard/billing",
	"/v1/dashboard/billing",
	"/console/topup",
	"/wallet",
	"/subscriptions",
	"/redemption-codes",
	"/oauth",
	"/sign-up",
	"/register",
}

var medHarnessBlockedExact = map[string]struct{}{
	"/api/user/register":                 {},
	"/api/user/aff":                      {},
	"/api/user/aff_transfer":             {},
	"/api/user/pay":                      {},
	"/api/user/amount":                   {},
	"/api/user/stripe/pay":               {},
	"/api/user/stripe/amount":            {},
	"/api/user/creem/pay":                {},
	"/api/user/waffo/pay":                {},
	"/api/user/waffo/amount":             {},
	"/api/user/waffo-pancake/pay":        {},
	"/api/user/waffo-pancake/amount":     {},
	"/api/option/payment_compliance":     {},
	"/api/user/epay/notify":              {},
	"/api/subscription/epay/notify":      {},
	"/api/subscription/epay/return":      {},
}

// InstallMedHarnessResaleGuard makes upstream resale/self-service surfaces
// unreachable in MedHarness deployments while keeping the subtree rebaseable.
func InstallMedHarnessResaleGuard(engine *gin.Engine) {
	if !common.GetEnvOrDefaultBool("MEDHARNESS_DISABLE_RESALE_SURFACE", true) {
		return
	}

	engine.Use(func(c *gin.Context) {
		path := normalizeMedHarnessPath(c.Request.URL.Path)
		if medHarnessPathBlocked(path) {
			c.AbortWithStatusJSON(http.StatusNotFound, gin.H{
				"error": gin.H{
					"code": "medharness_surface_disabled",
					"msg":  "endpoint disabled",
				},
			})
			return
		}
		c.Next()
	})
}

func normalizeMedHarnessPath(path string) string {
	normalized := strings.ToLower(path)
	if normalized != "/" {
		normalized = strings.TrimRight(normalized, "/")
	}
	if normalized == "" {
		return "/"
	}
	return normalized
}

func medHarnessPathBlocked(path string) bool {
	if _, ok := medHarnessBlockedExact[path]; ok {
		return true
	}
	for _, prefix := range medHarnessBlockedPrefixes {
		if path == prefix || strings.HasPrefix(path, prefix+"/") {
			return true
		}
	}
	return false
}

// medHarnessBypassPrefixes are surfaces that egress to upstream providers (or
// expose the bare control plane) WITHOUT transiting the §D.1 compliance spine.
// MedHarnessCompliance is mounted only on the gated /v1 relay group, so these
// alternate relay groups (Midjourney / Suno / Playground / Gemini-native /
// video / Kling / Jimeng) and the bare MCP control-plane routes would let a
// caller skip phi→desens→router→injection entirely (ADR-18 §5 "relay 旁路分支").
//
// Per ADR-18 §5 the fork hard-disables them (prefer "disable switch + route
// hide" over deep middleware weaving, to keep the rebase surface small). The
// nginx egress allowlist hides the off-/v1 surfaces at the DMZ, but the
// /v1/video* routes live in a SEPARATE ungated /v1 group (see
// router/video-router.go) under the allowlisted /v1/* prefix — so this guard is
// the ONLY enforcement point that can close them.
var medHarnessBypassPrefixes = []string{
	"/api/route", // bare model-router control plane — internal only (B1)
	"/api/audit", // bare audit-log control plane — internal only (B1)
	"/mj",        // Midjourney relay — bypasses §D.1
	"/suno",      // Suno relay — bypasses §D.1
	"/pg",        // Playground relay — bypasses §D.1
	"/v1beta",    // Gemini-native relay (+ native model list) — bypasses §D.1
	"/v1/video",  // video generations relay (ungated /v1 group) — bypasses §D.1
	"/v1/videos", // videos relay: create/remix/fetch/content — bypasses §D.1
	"/kling",     // Kling video relay — bypasses §D.1
	"/jimeng",    // Jimeng video relay — bypasses §D.1
}

// InstallMedHarnessBypassGuard hard-disables every relay / control-plane surface
// that would skip the §D.1 compliance gate, satisfying the ADR-18 §5 disable
// list. It runs as engine-level middleware (before route matching) so it closes
// the holes by path regardless of which gin group registered them. This is
// defense-in-depth with the nginx egress allowlist, and the sole enforcement
// point for the ungated /v1/video* routes the /v1/* allowlist would expose.
func InstallMedHarnessBypassGuard(engine *gin.Engine) {
	if !common.GetEnvOrDefaultBool("MEDHARNESS_DISABLE_BYPASS_SURFACE", true) {
		return
	}

	engine.Use(func(c *gin.Context) {
		if medHarnessBypassBlocked(normalizeMedHarnessPath(c.Request.URL.Path)) {
			c.AbortWithStatusJSON(http.StatusNotFound, gin.H{
				"error": gin.H{
					"code": "medharness_surface_disabled",
					"msg":  "endpoint disabled",
				},
			})
			return
		}
		c.Next()
	})
}

func medHarnessBypassBlocked(path string) bool {
	for _, prefix := range medHarnessBypassPrefixes {
		if path == prefix || strings.HasPrefix(path, prefix+"/") {
			return true
		}
	}
	// Dynamic Midjourney mode prefix: /:mode/mj/... (e.g. /fast/mj/submit/imagine).
	if strings.Contains(path, "/mj/") || strings.HasSuffix(path, "/mj") {
		return true
	}
	return false
}
