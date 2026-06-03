import { useEffect, useMemo, useState } from "react";

import Card from "@/components/Card";
import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type {
  ConfigProposeRequest,
  ConfigProposeResponse,
  ConfigSection,
  ConfigSnapshot,
  KV,
  Sanitized,
} from "@/api/contract";

import "./Policy.css";

type PolicyTab = "compliance" | "security" | "cost" | "governance";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; snapshots: Record<ConfigSection, Sanitized<ConfigSnapshot>> }
  | { status: "error" };

type DraftMap = Record<ConfigSection, string[]>;

type DiffLine = {
  kind: "a" | "c" | "d";
  text: string;
};

type FieldRow = Record<string, unknown> & {
  index: number;
  fieldKey: string;
  currentValue: string;
  proposedValue: string;
};

type ApprovalRow = Record<string, unknown> & {
  role: string;
  duty: string;
  approval: string;
  note: string;
};

type DialogState = {
  section: ConfigSection;
  reason: string;
  status: "editing" | "submitting" | "error";
};

type SubmissionState = {
  section: ConfigSection;
  result: Sanitized<ConfigProposeResponse>;
};

const TAB_SECTIONS: Record<PolicyTab, ConfigSection[]> = {
  compliance: ["scene", "models", "fields", "thresholds", "retention"],
  security: ["injection", "output"],
  cost: ["quota"],
  governance: ["upstream", "approval"],
};

const TAB_META: Record<PolicyTab, { label: string; note: string }> = {
  compliance: { label: "合规", note: "场景 / 模型 / 字段 / 阈值 / 留存" },
  security: { label: "安全", note: "注入防护 / 出站输出" },
  cost: { label: "成本护栏", note: "配额限流 · 暂未上线的能力标注「即将推出」" },
  governance: { label: "治理审批", note: "上游 / 审批 · 改动走 DIFF 预览" },
};

const APPROVAL_COLUMNS: TableColumn<ApprovalRow>[] = [
  { key: "role", header: "角色" },
  { key: "duty", header: "职责" },
  {
    key: "approval",
    header: "审批权",
    render: (row) => <Tag tone={row.role.includes("负责人") ? "compliance" : "muted"}>{row.approval}</Tag>,
  },
  { key: "note", header: "说明" },
];

const APPROVAL_ROWS: ApprovalRow[] = [
  {
    role: "研发负责人",
    duty: "主审批 / 发起",
    approval: "可提交审批",
    note: "高危变更默认主签。",
  },
  {
    role: "系统管理员",
    duty: "协办 / 只读",
    approval: "不可直批",
    note: "仅查看与补充材料。",
  },
];

function buildSnapshotMap(
  entries: ReadonlyArray<readonly [ConfigSection, Sanitized<ConfigSnapshot>]>,
): Record<ConfigSection, Sanitized<ConfigSnapshot>> {
  const map = {} as Record<ConfigSection, Sanitized<ConfigSnapshot>>;
  for (const [section, snapshot] of entries) {
    map[section] = snapshot;
  }
  return map;
}

function buildDraftMap(snapshots: Record<ConfigSection, Sanitized<ConfigSnapshot>>): DraftMap {
  const map = {} as DraftMap;
  for (const section of Object.keys(snapshots) as ConfigSection[]) {
    map[section] = snapshots[section].fields.map((field) => field.v);
  }
  return map;
}

function buildProposedFields(snapshot: Sanitized<ConfigSnapshot>, draft: string[]): KV[] {
  return snapshot.fields.map((field, index) => ({
    k: field.k,
    v: draft[index] ?? field.v,
  }));
}

function buildDiffLines(snapshot: Sanitized<ConfigSnapshot>, draft: string[]): DiffLine[] {
  const lines: DiffLine[] = [{ kind: "c", text: `# policies.yaml · ${snapshot.title}` }];

  snapshot.fields.forEach((field, index) => {
    const nextValue = draft[index] ?? field.v;
    if (nextValue === field.v) {
      lines.push({ kind: "c", text: `  ${field.k}: ${field.v}` });
      return;
    }
    lines.push({ kind: "d", text: `- ${field.k}: ${field.v}` });
    lines.push({ kind: "a", text: `+ ${field.k}: ${nextValue}` });
  });

  if (draft.length > snapshot.fields.length) {
    draft.slice(snapshot.fields.length).forEach((value, index) => {
      lines.push({ kind: "a", text: `+ field_${index + 1}: ${value}` });
    });
  }

  return lines;
}

function changeCount(snapshot: Sanitized<ConfigSnapshot>, draft: string[]): number {
  let count = 0;
  snapshot.fields.forEach((field, index) => {
    if ((draft[index] ?? field.v) !== field.v) count += 1;
  });
  if (draft.length > snapshot.fields.length) count += draft.length - snapshot.fields.length;
  return count;
}

function buildFieldColumns(
  section: ConfigSection,
  onDraftChange: (section: ConfigSection, index: number, value: string) => void,
): TableColumn<FieldRow>[] {
  return [
    { key: "fieldKey", header: "字段", mono: true },
    {
      key: "currentValue",
      header: "当前",
      mono: true,
      render: (row) => <span className="policy-current">{row.currentValue as string}</span>,
    },
    {
      key: "proposedValue",
      header: "提议",
      render: (row) => (
        <input
          aria-label={`${row.fieldKey} 的提议值`}
          className="policy-input"
          onChange={(event) => onDraftChange(section, row.index, event.target.value)}
          type="text"
          value={row.proposedValue as string}
        />
      ),
    },
  ];
}

function SectionCard({
  snapshot,
  draft,
  onDraftChange,
  onOpenApproval,
  submission,
}: {
  snapshot: Sanitized<ConfigSnapshot>;
  draft: string[];
  onDraftChange: (section: ConfigSection, index: number, value: string) => void;
  onOpenApproval: (section: ConfigSection) => void;
  submission?: Sanitized<ConfigProposeResponse>;
}): JSX.Element {
  const rows: FieldRow[] = useMemo(
    () =>
      snapshot.fields.map((field, index) => ({
        index,
        fieldKey: field.k,
        currentValue: field.v,
        proposedValue: draft[index] ?? field.v,
      })),
    [draft, snapshot.fields],
  );
  const diffLines = useMemo(() => buildDiffLines(snapshot, draft), [draft, snapshot]);
  const changed = useMemo(() => changeCount(snapshot, draft), [draft, snapshot]);
  const builtPlanned = snapshot.built === false;

  return (
    <Card eyebrow={snapshot.section} title={snapshot.title}>
      <div className="policy-card">
        <div className="policy-card-top">
          <div className="policy-card-tags">
            <Tag tone={builtPlanned ? "warn" : "ok"}>{builtPlanned ? "即将推出" : "已上线"}</Tag>
            <Tag tone="muted">{changed === 0 ? "无改动" : `变更 ${changed}`}</Tag>
            {submission ? <Tag tone="compliance">已提交审批·待批</Tag> : null}
          </div>
          <button className="policy-submit" onClick={() => onOpenApproval(snapshot.section)} type="button">
            提交审批
          </button>
        </div>

        <div className="policy-card-note">
          {builtPlanned ? "即将推出 · 暂未上线" : "读写均需走审批流；当前值来自真 ConfigSnapshot.fields。"}
        </div>

        <Table<FieldRow>
          columns={buildFieldColumns(snapshot.section, onDraftChange)}
          emptyLabel="暂无字段"
          getRowKey={(row) => `${snapshot.section}-${row.fieldKey}`}
          rows={rows}
        />

        <div className="policy-diff">
          <div className="policy-diff-head">
            <span>{snapshot.title} · DIFF 预览</span>
            <span className="policy-diff-count">{changed === 0 ? "无改动" : `${changed} 处变更`}</span>
          </div>
          <div className="policy-diff-block" aria-label={`${snapshot.title} diff preview`}>
            {diffLines.map((line, index) => (
              <div className={`policy-diff-line ${line.kind}`} key={`${snapshot.section}-${index}`}>
                {line.text}
              </div>
            ))}
          </div>
        </div>

        {submission ? (
          <div className="policy-submission">
            <Tag tone="compliance">已提交审批·待批</Tag>
            <span className="policy-submission-text">
              {submission.approval_id} · {submission.level} · {submission.status}
            </span>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export default function Policy(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [tab, setTab] = useState<PolicyTab>("compliance");
  const [drafts, setDrafts] = useState<DraftMap | null>(null);
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [submissions, setSubmissions] = useState<Partial<Record<ConfigSection, SubmissionState>>>({});

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void Promise.all(
      (Object.keys(TAB_SECTIONS) as PolicyTab[]).flatMap((policyTab) =>
        TAB_SECTIONS[policyTab].map(async (section) => [section, await requestEndpoint("config", { path: { section } })] as const),
      ),
    )
      .then((entries) => {
        if (!alive) return;
        const snapshots = buildSnapshotMap(entries);
        setState({ status: "ready", snapshots });
        setDrafts(buildDraftMap(snapshots));
      })
      .catch(() => {
        if (alive) setState({ status: "error" });
      });

    return () => {
      alive = false;
    };
  }, []);

  const currentSections = useMemo(() => {
    if (state.status !== "ready" || !drafts) return [];
    return TAB_SECTIONS[tab].map((section) => state.snapshots[section]);
  }, [drafts, state, tab]);

  const openApproval = (section: ConfigSection) => {
    if (state.status !== "ready") return;
    setDialog({
      section,
      reason: `调整 ${state.snapshots[section].title}`,
      status: "editing",
    });
  };

  const updateDraft = (section: ConfigSection, index: number, value: string) => {
    setDrafts((current) => {
      if (!current) return current;
      const next = { ...current };
      const values = [...next[section]];
      values[index] = value;
      next[section] = values;
      return next;
    });
  };

  const submitApproval = async () => {
    if (!dialog || state.status !== "ready" || !drafts) return;
    const snapshot = state.snapshots[dialog.section];
    const body: ConfigProposeRequest = {
      before: snapshot.fields,
      after: buildProposedFields(snapshot, drafts[dialog.section]),
      reason: dialog.reason.trim() || undefined,
    };

    setDialog({ ...dialog, status: "submitting" });

    try {
      const result = await requestEndpoint("configPropose", {
        path: { section: dialog.section },
        body,
      });
      setSubmissions((current) => ({
        ...current,
        [dialog.section]: { section: dialog.section, result },
      }));
      setDialog(null);
    } catch {
      setDialog({ ...dialog, status: "error" });
    }
  };

  const currentSubmission = dialog ? submissions[dialog.section] : undefined;

  return (
    <div className="policy-page">
      <div className="policy-head">
        <div>
          <div className="policy-kicker">⚙️ 策略</div>
          <h2>改动走 DIFF 预览 + 审批</h2>
          <div className="policy-subtitle">像 code review 一样看配置 · 只显示策略快照、哈希与审批结果。</div>
        </div>
        <div className="policy-badges">
          <Tag tone="muted">DIFF 预览</Tag>
          <Tag tone="compliance">全程 0 PHI</Tag>
          <Tag tone="cost">提交审批</Tag>
        </div>
      </div>

      <div className="policy-tabs" role="tablist" aria-label="策略分类">
        {Object.entries(TAB_META).map(([id, meta]) => (
          <button
            aria-selected={tab === id}
            className={tab === id ? "on" : ""}
            key={id}
            onClick={() => setTab(id as PolicyTab)}
            role="tab"
            type="button"
          >
            {meta.label}
          </button>
        ))}
      </div>

      {state.status === "error" ? (
        <div className="policy-error">请求失败</div>
      ) : state.status === "loading" || !drafts ? (
        <div className="policy-loading">加载中…</div>
      ) : (
        <div className="policy-stack">
          <div className="policy-tab-note">{TAB_META[tab].note}</div>

          {currentSections.length ? (
            <div className="policy-section-grid">
              {currentSections.map((snapshot) => (
                <SectionCard
                  draft={drafts[snapshot.section]}
                  key={snapshot.section}
                  onDraftChange={updateDraft}
                  onOpenApproval={openApproval}
                  snapshot={snapshot}
                  submission={submissions[snapshot.section]?.result}
                />
              ))}
            </div>
          ) : null}

          <section className="policy-summary">
            <Card title="治理提示">
              <div className="policy-summary-list">
                <div>
                  <b>写口</b>
                  <span>只产 approval_id，不直接改配置</span>
                </div>
                <div>
                  <b>审批前</b>
                  <span>不生效、可回滚、落审计</span>
                </div>
                <div>
                  <b>角色</b>
                  <span>研发负责人 / 系统管理员</span>
                </div>
              </div>
            </Card>
          </section>
        </div>
      )}

      {dialog ? (
        <div className="policy-modal-backdrop" role="presentation">
          <div className="policy-modal" role="dialog" aria-modal="true" aria-label="提交审批">
            <button className="policy-modal-close" onClick={() => setDialog(null)} type="button">
              ×
            </button>
            <div className="policy-modal-head">
              <div>
                <div className="policy-modal-kicker">提交审批</div>
                <h3>{state.status === "ready" ? state.snapshots[dialog.section].title : "配置变更"}</h3>
                <div className="policy-modal-subtitle">审批前不生效 · 以 DIFF 预览呈现改动。</div>
              </div>
              <div className="policy-modal-tags">
                <Tag tone="compliance">研发负责人</Tag>
                <Tag tone="muted">系统管理员</Tag>
              </div>
            </div>

            <div className="policy-modal-grid">
              <section className="policy-modal-body">
                <div className="policy-modal-field">
                  <label htmlFor="policy-reason">变更原因</label>
                  <textarea
                    id="policy-reason"
                    onChange={(event) => setDialog({ ...dialog, reason: event.target.value, status: "editing" })}
                    placeholder="输入审批说明"
                    value={dialog.reason}
                  />
                </div>

                <div className="policy-diff">
                  <div className="policy-diff-head">
                    <span>审批预览</span>
                    <span className="policy-diff-count">{state.status === "ready" ? state.snapshots[dialog.section].section : ""}</span>
                  </div>
                  <div className="policy-diff-block">
                    {state.status === "ready"
                      ? buildDiffLines(state.snapshots[dialog.section], drafts?.[dialog.section] ?? []).map((line, index) => (
                          <div className={`policy-diff-line ${line.kind}`} key={`modal-${index}`}>
                            {line.text}
                          </div>
                        ))
                      : null}
                  </div>
                </div>

                {dialog.status === "error" ? <div className="policy-dialog-error">提交失败，请重试。</div> : null}
                {currentSubmission ? (
                  <div className="policy-dialog-result">
                    <Tag tone="compliance">已提交审批·待批</Tag>
                    <span>
                      {currentSubmission.result.approval_id} · {currentSubmission.result.level}
                    </span>
                  </div>
                ) : null}
              </section>

              <aside className="policy-modal-side">
                <Card title="2 角色审批矩阵">
                  <Table<ApprovalRow>
                    columns={APPROVAL_COLUMNS}
                    emptyLabel="暂无审批矩阵"
                    getRowKey={(row) => row.role}
                    rows={APPROVAL_ROWS}
                  />
                </Card>
                <div className="policy-modal-note">
                  高危变更即使可点，也需按风险走审批；审批前不生效，审批后才进入后端 Hook。
                </div>
              </aside>
            </div>

            <div className="policy-modal-actions">
              <button className="policy-modal-cancel" onClick={() => setDialog(null)} type="button">
                取消
              </button>
              <button
                className="policy-modal-submit"
                disabled={dialog.status === "submitting"}
                onClick={submitApproval}
                type="button"
              >
                {dialog.status === "submitting" ? "提交中…" : "确认提交"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
