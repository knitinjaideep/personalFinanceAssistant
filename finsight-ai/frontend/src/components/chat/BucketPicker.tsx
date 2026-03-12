/**
 * BucketPicker — multi-select bucket scope for the chat screen.
 *
 * Lets the user query one bucket, multiple buckets, or all buckets.
 */

import React from "react";
import { clsx } from "clsx";
import { Globe, Check } from "lucide-react";
import type { Bucket } from "../../types";

interface BucketPickerProps {
  buckets: Bucket[];
  selectedIds: string[];         // empty = all buckets
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  disabled?: boolean;
}

export function BucketPicker({
  buckets,
  selectedIds,
  onToggle,
  onSelectAll,
  disabled = false,
}: BucketPickerProps) {
  const allSelected = selectedIds.length === 0;

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {/* All buckets pill */}
      <button
        type="button"
        onClick={onSelectAll}
        disabled={disabled}
        className={clsx(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
          "border focus:outline-none",
          allSelected
            ? "bg-blue-600 text-white border-blue-600"
            : "bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <Globe size={11} />
        All
      </button>

      {/* Individual bucket pills */}
      {buckets.map((bucket) => {
        const active = selectedIds.includes(bucket.id);
        return (
          <button
            key={bucket.id}
            type="button"
            onClick={() => onToggle(bucket.id)}
            disabled={disabled}
            className={clsx(
              "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
              "border focus:outline-none",
              active
                ? "text-white border-transparent"
                : "bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600",
              disabled && "opacity-50 cursor-not-allowed"
            )}
            style={active ? { backgroundColor: bucket.color, borderColor: bucket.color } : {}}
          >
            {active && <Check size={10} />}
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: active ? "rgba(255,255,255,0.6)" : bucket.color }}
            />
            {bucket.name}
          </button>
        );
      })}
    </div>
  );
}
