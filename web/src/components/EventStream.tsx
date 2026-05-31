import Tag from "./Tag";
import "./EventStream.css";

type EventTone = "compliance" | "security";

type EventChipTone = "compliance" | "security" | "cost" | "muted" | "ok" | "warn" | "bad";

type EventChip = {
  label: string;
  tone?: EventChipTone;
};

type EventItem = {
  tone?: EventTone;
  title: string;
  time: string;
  category: string;
  chips?: EventChip[];
};

type EventStreamProps = {
  events: EventItem[];
  maxHeight?: number;
};

const toneClass: Record<EventTone, string> = {
  compliance: "comp",
  security: "sec",
};

const toneLabel: Record<EventTone, string> = {
  compliance: "合规",
  security: "安全",
};

export default function EventStream({ events, maxHeight = 380 }: EventStreamProps) {
  return (
    <div className="events" style={{ maxHeight }}>
      {events.length ? (
        events.map((event, index) => (
          <article
            key={`${event.time}-${index}`}
            className={event.tone ? `ev ${toneClass[event.tone]}` : "ev"}
          >
            <div
              className={event.tone ? `ev-dot ${toneClass[event.tone]}` : "ev-dot"}
              aria-hidden="true"
            />
            <div className="ev-body">
              <div className="ev-title">{event.title}</div>
              <div className="ev-meta">
                <span className="ev-time">{event.time}</span>
                <span aria-hidden="true">·</span>
                <span>{event.tone ? toneLabel[event.tone] : "事件"}</span>
                <span aria-hidden="true">·</span>
                <span>{event.category}</span>
              </div>
              <div className="ev-chiprow">
                {(event.chips ?? []).map((chip) => (
                  <span className="ev-chip" key={chip.label}>
                    <Tag tone={chip.tone ?? "muted"}>{chip.label}</Tag>
                  </span>
                ))}
              </div>
            </div>
          </article>
        ))
      ) : (
        <div className="ev-empty">暂无事件</div>
      )}
    </div>
  );
}
