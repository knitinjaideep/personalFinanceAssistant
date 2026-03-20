import { Upload, Loader2, CheckCircle2 } from "lucide-react";
import { clsx } from "clsx";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";
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
      setTimeout(() => setJustUploaded(false), 2500);
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

  const state = uploading ? "uploading" : justUploaded ? "success" : isDragActive ? "drag" : "idle";

  return (
    <motion.div
      {...(getRootProps() as any)}
      className={clsx(
        "relative rounded-3xl border-2 p-10 text-center cursor-pointer overflow-hidden",
        "transition-colors duration-300",
        state === "idle"     && "upload-idle",
        state === "drag"     && "upload-active",
        state === "uploading"&& "border-ocean-200 bg-white/80 cursor-wait",
        state === "success"  && "upload-success"
      )}
      whileHover={state === "idle" ? { scale: 1.005 } : undefined}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      style={{ backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}
    >
      <input {...getInputProps()} />

      {/* Glow overlay on drag */}
      <AnimatePresence>
        {state === "drag" && (
          <motion.div
            className="absolute inset-0 rounded-3xl pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              background: "radial-gradient(ellipse at 50% 50%, rgba(255,122,90,0.12), transparent 70%)",
            }}
          />
        )}
      </AnimatePresence>

      <div className="flex flex-col items-center gap-4 relative z-10">
        <AnimatePresence mode="wait">
          {state === "uploading" && (
            <motion.div
              key="uploading"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="flex flex-col items-center gap-3"
            >
              <Loader2 size={36} className="text-ocean animate-spin" />
              <p className="text-sm font-semibold text-ocean">Uploading & parsing…</p>
            </motion.div>
          )}

          {state === "success" && (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
              className="flex flex-col items-center gap-3"
            >
              <motion.div
                animate={{ scale: [1, 1.15, 1] }}
                transition={{ duration: 0.5, ease: "easeInOut" }}
              >
                <CheckCircle2 size={40} className="text-positive" />
              </motion.div>
              <p className="text-sm font-semibold text-positive">Upload complete!</p>
            </motion.div>
          )}

          {state === "drag" && (
            <motion.div
              key="drag"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-3"
            >
              <Upload size={36} className="text-coral" />
              <p className="text-sm font-semibold text-coral">Drop files here</p>
            </motion.div>
          )}

          {state === "idle" && (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-4"
            >
              {/* Floating upload icon */}
              <motion.div
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 3, ease: "easeInOut", repeat: Infinity }}
                className="p-4 rounded-2xl bg-coral-50 text-coral border border-coral-100/60 shadow-soft"
              >
                <Upload size={26} />
              </motion.div>

              <div>
                <p className="text-sm font-bold text-ocean-deep">
                  Drag & drop financial statement PDFs
                </p>
                <p className="text-xs text-ocean/50 mt-1.5">
                  Morgan Stanley · Chase · E*TRADE · Amex · Discover
                </p>
              </div>

              <span className="text-xs px-5 py-2 rounded-full btn-coral font-semibold">
                Browse files
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
