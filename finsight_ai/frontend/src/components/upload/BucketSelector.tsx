/**
 * BucketSelector — inline bucket picker with "create new" support.
 *
 * Used in the upload flow to assign files to a bucket before or after upload.
 */

import React, { useState } from "react";
import { Plus, ChevronDown, Folder, X } from "lucide-react";
import { clsx } from "clsx";
import type { Bucket, BucketCreateRequest } from "../../types";

const PRESET_COLORS = [
  "#3b82f6", // blue
  "#10b981", // green
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#f97316", // orange
  "#64748b", // slate
];

interface BucketSelectorProps {
  buckets: Bucket[];
  selectedBucketId: string | null;
  onSelect: (bucketId: string | null) => void;
  onCreateBucket: (request: BucketCreateRequest) => Promise<Bucket | null>;
  isCreating?: boolean;
  disabled?: boolean;
}

export function BucketSelector({
  buckets,
  selectedBucketId,
  onSelect,
  onCreateBucket,
  isCreating = false,
  disabled = false,
}: BucketSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(PRESET_COLORS[0]);

  const selected = buckets.find((b) => b.id === selectedBucketId) ?? null;

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;

    const request: BucketCreateRequest = { name, color: newColor };
    const bucket = await onCreateBucket(request);
    if (bucket) {
      onSelect(bucket.id);
      setNewName("");
      setNewColor(PRESET_COLORS[0]);
      setShowCreate(false);
      setIsOpen(false);
    }
  };

  return (
    <div className="relative">
      {/* Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((o) => !o)}
        className={clsx(
          "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm w-full",
          "transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500",
          disabled
            ? "opacity-50 cursor-not-allowed bg-gray-50 border-gray-200"
            : "bg-white border-gray-300 hover:border-blue-400 cursor-pointer"
        )}
      >
        {selected ? (
          <>
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: selected.color }}
            />
            <span className="flex-1 text-left text-gray-800 truncate">
              {selected.name}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(null);
              }}
              className="text-gray-400 hover:text-gray-600"
            >
              <X size={12} />
            </button>
          </>
        ) : (
          <>
            <Folder size={14} className="text-gray-400 shrink-0" />
            <span className="flex-1 text-left text-gray-400">
              Assign to bucket…
            </span>
            <ChevronDown size={14} className="text-gray-400 shrink-0" />
          </>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          {/* Existing buckets */}
          {buckets.length > 0 && (
            <div className="max-h-48 overflow-y-auto">
              {buckets.map((bucket) => (
                <button
                  key={bucket.id}
                  type="button"
                  onClick={() => {
                    onSelect(bucket.id);
                    setIsOpen(false);
                    setShowCreate(false);
                  }}
                  className={clsx(
                    "w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-gray-50 transition-colors",
                    bucket.id === selectedBucketId && "bg-blue-50"
                  )}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: bucket.color }}
                  />
                  <span className="flex-1 truncate text-gray-800">
                    {bucket.name}
                  </span>
                  <span className="text-xs text-gray-400">
                    {bucket.document_count} doc{bucket.document_count !== 1 ? "s" : ""}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Divider */}
          {buckets.length > 0 && <div className="border-t border-gray-100" />}

          {/* Create new */}
          {!showCreate ? (
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 transition-colors"
            >
              <Plus size={14} />
              Create new bucket
            </button>
          ) : (
            <div className="p-3 space-y-2">
              <input
                autoFocus
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleCreate();
                  if (e.key === "Escape") setShowCreate(false);
                }}
                placeholder="Bucket name…"
                className="w-full px-2.5 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {/* Color picker */}
              <div className="flex gap-1.5 flex-wrap">
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setNewColor(c)}
                    className={clsx(
                      "w-5 h-5 rounded-full border-2 transition-all",
                      newColor === c
                        ? "border-gray-800 scale-110"
                        : "border-transparent hover:scale-105"
                    )}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!newName.trim() || isCreating}
                  className="flex-1 px-2.5 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {isCreating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
