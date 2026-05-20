## 概要
1-2 句说明这个 PR 做了什么。

## 类型
- [ ] feat：新功能
- [ ] fix：bug 修复
- [ ] docs：文档
- [ ] refactor：重构（无功能变化）
- [ ] test：测试加固
- [ ] chore：构建 / 依赖
- [ ] compliance：合规规则调整（需双委员会签字）

## 涉及范围
- [ ] Skill
- [ ] Sub-agent
- [ ] MCP server
- [ ] Hook
- [ ] SOP
- [ ] fields.yml
- [ ] 培训 / 文档
- [ ] 治理 / License

## 合规自检（必填 · 5 问）

1. 本 PR **是否会让 PHI 进入 prompt 路径**？
   - [ ] 否
   - [ ] 是，已前置 `phi-desensitize`

2. 本 PR **是否新增 LLM 调用**？
   - [ ] 否
   - [ ] 是，已走 `mcp-model-router`

3. 本 PR **是否绕过任何 Hook**？
   - [ ] 否
   - [ ] 是，双委员会签字 issue：#____

4. 本 PR **是否处理真实生产数据**？
   - [ ] 否
   - [ ] 是，已 100% 合成 + 指纹核验

5. 本 PR **是否影响审计血缘**？
   - [ ] 否
   - [ ] 是，AUDIT_BUNDLE schema 已更新

## 测试

- [ ] `pytest tests/integration/` 通过
- [ ] `bash dryrun_e2e_v2.sh` 通过（产出 AUDIT_BUNDLE 哈希正常）
- [ ] `bash tests/red-team-drills/run_all.sh` 通过（如改动合规规则）
- [ ] 我已自测，提供 reviewer 必看的关键日志（贴在评论）

## 文档

- [ ] 修改的 Skill / Hook / SOP 已同步更新 README / docs
- [ ] CHANGELOG.md 已添加条目

## 相关 issue
Closes #____

## 给 reviewer 的话
（必看哪里 / 已知 trade-off / 期望反馈）
