import type { KeyboardEvent, ReactNode } from "react";

import "./Table.css";

type TableAlign = "left" | "center" | "right";

export type TableColumn<T extends Record<string, unknown>> = {
  key: keyof T & string;
  header: ReactNode;
  mono?: boolean;
  align?: TableAlign;
  render?: (row: T, index: number) => ReactNode;
};

type TableProps<T extends Record<string, unknown>> = {
  columns: TableColumn<T>[];
  rows: T[];
  onRowClick?: (row: T, index: number) => void;
  getRowKey?: (row: T, index: number) => string | number;
  emptyLabel?: string;
};

const alignClass: Record<TableAlign, string> = {
  left: "",
  center: "dtable-align-center",
  right: "dtable-align-right",
};

function cellClass<T extends Record<string, unknown>>(column: TableColumn<T>): string | undefined {
  const classes = [column.mono ? "dtable-mono" : "", alignClass[column.align ?? "left"]].filter(
    Boolean,
  );
  return classes.length ? classes.join(" ") : undefined;
}

function renderValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number") return value;
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export default function Table<T extends Record<string, unknown>>({
  columns,
  rows,
  onRowClick,
  getRowKey,
  emptyLabel = "暂无数据",
}: TableProps<T>) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (!onRowClick) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onRowClick(row, index);
  };

  return (
    <div className="dtable-scroll">
      <table className="dtable">
        <thead>
          <tr>
            {columns.map((column) => (
              <th className={cellClass(column)} key={column.key} scope="col">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, index) => (
              <tr
                className={onRowClick ? "click" : undefined}
                key={getRowKey ? getRowKey(row, index) : index}
                onClick={onRowClick ? () => onRowClick(row, index) : undefined}
                onKeyDown={(event) => handleKeyDown(event, row, index)}
                role={onRowClick ? "button" : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                aria-label={onRowClick ? `表格行 ${index + 1}` : undefined}
              >
                {columns.map((column) => (
                  <td className={cellClass(column)} key={column.key}>
                    {column.render ? column.render(row, index) : renderValue(row[column.key])}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td className="dtable-empty" colSpan={columns.length}>
                {emptyLabel}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
