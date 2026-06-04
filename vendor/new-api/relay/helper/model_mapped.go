package helper

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/QuantumNous/new-api/constant"
	"github.com/QuantumNous/new-api/dto"
	"github.com/QuantumNous/new-api/relay/common"
	relayconstant "github.com/QuantumNous/new-api/relay/constant"
	"github.com/QuantumNous/new-api/setting/ratio_setting"
	"github.com/gin-gonic/gin"
)

func ModelMappedHelper(c *gin.Context, info *common.RelayInfo, request dto.Request) error {
	if info.ChannelMeta == nil {
		info.ChannelMeta = &common.ChannelMeta{}
	}

	isResponsesCompact := info.RelayMode == relayconstant.RelayModeResponsesCompact
	originModelName := info.OriginModelName
	mappingModelName := originModelName
	if isResponsesCompact && strings.HasSuffix(originModelName, ratio_setting.CompactModelSuffix) {
		mappingModelName = strings.TrimSuffix(originModelName, ratio_setting.CompactModelSuffix)
	}

	// map model name
	modelMapping := c.GetString("model_mapping")
	if modelMapping != "" && modelMapping != "{}" {
		modelMap := make(map[string]string)
		err := json.Unmarshal([]byte(modelMapping), &modelMap)
		if err != nil {
			return fmt.Errorf("unmarshal_model_mapping_failed")
		}

		// 支持链式模型重定向，最终使用链尾的模型
		currentModel := mappingModelName
		visitedModels := map[string]bool{
			currentModel: true,
		}
		for {
			if mappedModel, exists := modelMap[currentModel]; exists && mappedModel != "" {
				// 模型重定向循环检测，避免无限循环
				if visitedModels[mappedModel] {
					if mappedModel == currentModel {
						if currentModel == info.OriginModelName {
							info.IsModelMapped = false
							return nil
						} else {
							info.IsModelMapped = true
							break
						}
					}
					return errors.New("model_mapping_contains_cycle")
				}
				visitedModels[mappedModel] = true
				currentModel = mappedModel
				info.IsModelMapped = true
			} else {
				break
			}
		}
		if info.IsModelMapped {
			info.UpstreamModelName = currentModel
		}
	}

	if isResponsesCompact {
		finalUpstreamModelName := mappingModelName
		if info.IsModelMapped && info.UpstreamModelName != "" {
			finalUpstreamModelName = info.UpstreamModelName
		}
		info.UpstreamModelName = finalUpstreamModelName
		info.OriginModelName = ratio_setting.WithCompactModelSuffix(finalUpstreamModelName)
	}
	// BE-7.3 (§D.1 "base has no autonomy"): once the effective upstream model is
	// resolved (after any model_mapping chain), fail closed if it falls outside the
	// policy-vetted allowed_model_set stamped by middleware.MedHarnessCompliance.
	// A channel's model_mapping must not exfiltrate the request to a model the
	// policy never approved. No-op when no set is stamped (non-MedHarness paths).
	if err := enforceMedHarnessAllowlist(c, info); err != nil {
		return err
	}

	if request != nil {
		request.SetModelName(info.UpstreamModelName)
	}
	return nil
}

// enforceMedHarnessAllowlist returns a generic, non-leaking error when the
// resolved effective upstream model is not in the context-stamped
// allowed_model_set. When no set is present (or it is empty) it is a no-op, so
// upstream behavior is preserved for non-MedHarness deployments.
func enforceMedHarnessAllowlist(c *gin.Context, info *common.RelayInfo) error {
	if c == nil {
		return nil
	}
	value, exists := c.Get(string(constant.ContextKeyMedHarnessAllowedModelSet))
	if !exists {
		return nil
	}
	allowed, ok := value.(map[string]bool)
	if !ok || len(allowed) == 0 {
		return nil
	}
	effectiveModel := info.UpstreamModelName
	if effectiveModel == "" {
		effectiveModel = info.OriginModelName
	}
	if !allowed[effectiveModel] {
		return errors.New("medharness_model_outside_allowlist")
	}
	return nil
}
