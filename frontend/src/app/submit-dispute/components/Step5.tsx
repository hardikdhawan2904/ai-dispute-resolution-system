"use client";

import { useRef, useEffect, useState } from "react";
import {
  Upload, X, FileText, Image as ImageIcon, FileSpreadsheet, File,
  Lock, AlertCircle, CheckCircle2,
} from "lucide-react";
import { Panel, SubSection } from "./FormControls";
import { getDocumentRequirements } from "@/lib/api";

interface Step5Props {
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  disputeReason: string;
  fraudSelected: boolean;
  amount: number;
  error?: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText className="w-4 h-4 text-red-500" />;
  if (ext === "jpg" || ext === "jpeg" || ext === "png")
    return <ImageIcon className="w-4 h-4 text-blue-500" />;
  if (ext === "xlsx" || ext === "csv")
    return <FileSpreadsheet className="w-4 h-4 text-green-600" />;
  return <File className="w-4 h-4 text-slate-400" />;
}

export default function Step5({
  files, onAdd, onRemove,
  disputeReason, fraudSelected, amount,
  error,
}: Step5Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [requiredDocs, setRequiredDocs]   = useState<string[]>([]);
  const [docsCategory, setDocsCategory]   = useState("");
  const [loadingDocs, setLoadingDocs]     = useState(false);

  // Fetch required documents whenever dispute details change
  useEffect(() => {
    if (!disputeReason) return;
    setLoadingDocs(true);
    getDocumentRequirements(disputeReason, fraudSelected, amount)
      .then((result) => {
        if (result) {
          setRequiredDocs(result.required_documents);
          setDocsCategory(result.category);
        }
      })
      .finally(() => setLoadingDocs(false));
  }, [disputeReason, fraudSelected, amount]);

  function handleFiles(selected: FileList | null) {
    if (!selected) return;
    const newFiles = Array.from(selected).filter((f) => f.size <= 10 * 1024 * 1024);
    onAdd(newFiles);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  }

  const hasImage = files.some((f) => /\.(jpg|jpeg|png)$/i.test(f.name));

  return (
    <div className="space-y-4">

      {/* ── Required Documents ────────────────────────────────────────────── */}
      <Panel label={docsCategory ? `Required Documents — ${docsCategory}` : "Required Documents"}>
        {loadingDocs ? (
          <p className="text-xs text-slate-400 py-2">Loading document requirements…</p>
        ) : requiredDocs.length > 0 ? (
          <>
            <p className="text-xs text-slate-500 mb-3 leading-relaxed">
              The following documents are required for your dispute type.
              Missing any of these may delay your case or cause it to be held for further information.
            </p>
            <div className="space-y-1.5">
              {requiredDocs.map((doc, i) => {
                const uploaded = files.some((f) =>
                  f.name.toLowerCase().includes(doc.split(" ")[0].toLowerCase())
                );
                return (
                  <div
                    key={i}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded border ${
                      uploaded
                        ? "border-green-200 bg-green-50"
                        : "border-amber-200 bg-amber-50"
                    }`}
                  >
                    {uploaded
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                      : <AlertCircle  className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    }
                    <span className={`text-xs ${uploaded ? "text-green-800" : "text-amber-800"}`}>
                      {doc}
                    </span>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <p className="text-xs text-slate-400 py-2">
            Complete Step 3 (Dispute Details) to see required documents for your case.
          </p>
        )}
      </Panel>

      {/* ── Upload ────────────────────────────────────────────────────────── */}
      <Panel label="Upload Supporting Documents *">
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/20 transition-colors group"
        >
          <div className="w-11 h-11 rounded-lg bg-blue-50 flex items-center justify-center mx-auto mb-3 group-hover:bg-blue-100 transition-colors">
            <Upload className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-sm font-semibold text-slate-700 mb-1">
            Drag &amp; drop files, or click to browse
          </p>
          <p className="text-xs text-slate-400">
            PDF, JPG, PNG, XLSX, CSV — Maximum 10 MB per file
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.xlsx,.csv"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {files.length > 0 && (
          <div className="mt-4">
            <SubSection label={`${files.length} Document${files.length > 1 ? "s" : ""} Attached`}>
              <div className="space-y-2">
                {files.map((file, idx) => (
                  <div
                    key={`${file.name}-${idx}`}
                    className="flex items-center gap-3 px-4 py-2.5 bg-white border border-slate-200 rounded-lg"
                  >
                    <FileIcon name={file.name} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-800 truncate">{file.name}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">{formatBytes(file.size)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onRemove(idx)}
                      className="w-6 h-6 rounded-md bg-slate-100 hover:bg-red-100 hover:text-red-600 flex items-center justify-center text-slate-400 transition-colors shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </SubSection>
          </div>
        )}

        <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 text-amber-500" />
          At least one image proof (JPG or PNG) is required to submit your dispute.
          {!hasImage && files.length > 0 && (
            <span className="text-red-500 font-medium ml-1">No image uploaded yet.</span>
          )}
        </p>

        {error && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-red-600 font-medium">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {error}
          </p>
        )}
      </Panel>

      {/* ── Security notice ───────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 border border-slate-200 bg-slate-50/80 rounded-lg px-4 py-3.5">
        <Lock className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mb-1">
            Document Security
          </p>
          <p className="text-xs text-slate-500 leading-relaxed">
            All uploaded documents are encrypted at rest and in transit using AES-256.
            Files are retained for 90 days as required under RBI record-keeping guidelines,
            after which they are permanently deleted from all systems.
          </p>
        </div>
      </div>

    </div>
  );
}
