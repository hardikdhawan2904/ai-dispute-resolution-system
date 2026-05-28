"use client";

import { useRef } from "react";
import {
  Upload,
  X,
  FileText,
  Image,
  FileSpreadsheet,
  File,
  Lock,
  Info,
} from "lucide-react";
import { Panel, SubSection } from "./FormControls";

interface Step5Props {
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  suggestions: string[];
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
    return <Image className="w-4 h-4 text-blue-500" />;
  if (ext === "xlsx" || ext === "xls")
    return <FileSpreadsheet className="w-4 h-4 text-green-600" />;
  return <File className="w-4 h-4 text-slate-400" />;
}

const FALLBACK_SUGGESTIONS = [
  "Bank statement",
  "Transaction screenshot",
  "Merchant communication",
  "Receipt or invoice",
];

export default function Step5({ files, onAdd, onRemove, suggestions }: Step5Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(selected: FileList | null) {
    if (!selected) return;
    const newFiles = Array.from(selected).filter((f) => f.size <= 10 * 1024 * 1024);
    onAdd(newFiles);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  }

  const displaySuggestions = suggestions.length > 0 ? suggestions : FALLBACK_SUGGESTIONS;

  return (
    <div className="space-y-4">

      {/* ── Recommended Documents ─────────────────────────────────────────── */}
      <Panel label="Recommended Documents">
        <p className="text-xs text-slate-500 mb-4 leading-relaxed">
          Based on your dispute type, the following documents will materially accelerate case resolution and reduce the likelihood of information requests during investigation.
        </p>
        <div className="space-y-1.5">
          {displaySuggestions.map((s) => (
            <div
              key={s}
              className="flex items-center gap-2.5 px-3 py-2 rounded border border-gray-200 bg-gray-50"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-gray-400 shrink-0" />
              <span className="text-xs text-gray-700">{s}</span>
            </div>
          ))}
        </div>
      </Panel>

      {/* ── Upload ────────────────────────────────────────────────────────── */}
      <Panel label="Upload Supporting Documents">

        {/* Drop zone */}
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
            PDF, JPG, PNG, XLSX — Maximum 10 MB per file
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.xlsx"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {/* File list */}
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
                      <p className="text-xs font-semibold text-slate-800 truncate">
                        {file.name}
                      </p>
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

        {files.length === 0 && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
            <Info className="w-3.5 h-3.5 shrink-0" />
            Documents are optional but significantly improve resolution speed and accuracy.
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
            All uploaded documents are encrypted at rest and in transit using AES-256. Files are retained for 90 days as required under RBI record-keeping guidelines, after which they are permanently deleted from all systems.
          </p>
        </div>
      </div>

    </div>
  );
}
