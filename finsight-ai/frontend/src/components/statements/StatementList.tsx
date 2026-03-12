import React, { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Statement } from "../../types";
import { Loader2, FileText, CheckCircle, AlertCircle, Clock } from "lucide-react";
import { clsx } from "clsx";
import { format, parseISO } from "date-fns";

const STATUS_ICONS: Record<string, React.ReactNode> = {
  success: <CheckCircle size={14} className="text-green-500" />,
  partial: <AlertCircle size={14} className="text-yellow-500" />,
  failed: <AlertCircle size={14} className="text-red-500" />,
  pending: <Clock size={14} className="text-gray-400" />,
};

export function StatementList() {
  const [statements, setStatements] = useState<Statement[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api
      .get<Statement[]>("/statements/")
      .then(setStatements)
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="animate-spin text-gray-400" />
      </div>
    );
  }

  if (statements.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <FileText size={40} className="mx-auto mb-3 text-gray-200" />
        <p className="text-sm">No statements yet.</p>
        <p className="text-xs mt-1">Upload financial statements to get started.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-gray-500 uppercase tracking-wide">
            <th className="pb-3 pr-4">Type</th>
            <th className="pb-3 pr-4">Period</th>
            <th className="pb-3 pr-4">Status</th>
            <th className="pb-3 text-right">Confidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {statements.map((s) => (
            <tr key={s.id} className="hover:bg-gray-50 transition-colors">
              <td className="py-3 pr-4">
                <span className="font-medium text-gray-800">
                  {s.statement_type.replace("_", " ")}
                </span>
              </td>
              <td className="py-3 pr-4 text-gray-500 text-xs">
                {format(parseISO(s.period_start), "MMM d")} –{" "}
                {format(parseISO(s.period_end), "MMM d, yyyy")}
              </td>
              <td className="py-3 pr-4">
                <div className="flex items-center gap-1.5">
                  {STATUS_ICONS[s.extraction_status] ?? STATUS_ICONS.pending}
                  <span
                    className={clsx("text-xs", {
                      "text-green-600": s.extraction_status === "success",
                      "text-yellow-600": s.extraction_status === "partial",
                      "text-red-600": s.extraction_status === "failed",
                      "text-gray-400": s.extraction_status === "pending",
                    })}
                  >
                    {s.extraction_status}
                  </span>
                </div>
              </td>
              <td className="py-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  <div className="w-16 bg-gray-100 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full bg-blue-500"
                      style={{ width: `${Math.round(s.overall_confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500 w-8 text-right">
                    {Math.round(s.overall_confidence * 100)}%
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
