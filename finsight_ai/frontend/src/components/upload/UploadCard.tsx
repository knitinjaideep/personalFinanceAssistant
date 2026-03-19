import { Upload, Loader2, CheckCircle } from "lucide-react";
import { clsx } from "clsx";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import type { DocumentUploadResponse } from "../../types";

interface UploadCardProps {
  onUploaded: () => void;
}

export function UploadCard({ onUploaded }: UploadCardProps) {
  const [uploading, setUploading] = useState(false);
  const [justUploaded, setJustUploaded] = useState(false);

  const onDrop = useCallback(
    async (files: File[]) => {
      setUploading(true);
      for (const file of files) {
        try {
          await api.upload<DocumentUploadResponse>("/documents/upload", file);
          toast.success(`Uploaded ${file.name}`);
        } catch (err: any) {
          toast.error(`Failed: ${err.detail || err.message}`);
        }
      }
      setUploading(false);
      setJustUploaded(true);
      setTimeout(() => setJustUploaded(false), 2000);
      onUploaded();
    },
    [onUploaded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: uploading,
  });

  return (
    <div
      {...getRootProps()}
      className={clsx(
        "relative rounded-2xl border-2 border-dashed p-10 text-center cursor-pointer transition-all duration-200 group",
        isDragActive
          ? "border-coral bg-coral-50 scale-[1.01]"
          : uploading
          ? "border-ocean-200 bg-ocean-50 cursor-wait"
          : justUploaded
          ? "border-positive bg-positive/5"
          : "border-ocean-100 bg-white hover:border-coral/50 hover:bg-coral-50/30"
      )}
    >
      <input {...getInputProps()} />

      <div className="flex flex-col items-center gap-3">
        {uploading ? (
          <>
            <Loader2
              size={36}
              className="text-ocean animate-spin"
            />
            <p className="text-sm font-medium text-ocean">
              Uploading & parsing...
            </p>
          </>
        ) : justUploaded ? (
          <>
            <CheckCircle size={36} className="text-positive" />
            <p className="text-sm font-medium text-positive">
              Upload complete!
            </p>
          </>
        ) : isDragActive ? (
          <>
            <Upload size={36} className="text-coral" />
            <p className="text-sm font-medium text-coral">
              Drop files here
            </p>
          </>
        ) : (
          <>
            <div className="p-3 rounded-2xl bg-coral-50 text-coral group-hover:bg-coral-100 transition-colors">
              <Upload size={28} />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate">
                Drag & drop financial statement PDFs
              </p>
              <p className="text-xs text-ocean-DEFAULT/50 mt-1">
                Supports Morgan Stanley, Chase, E*TRADE, Amex, Discover
              </p>
            </div>
            <span className="text-xs px-4 py-1.5 rounded-full border border-coral/30 text-coral font-medium group-hover:bg-coral group-hover:text-white group-hover:border-coral transition-all">
              Browse files
            </span>
          </>
        )}
      </div>
    </div>
  );
}
