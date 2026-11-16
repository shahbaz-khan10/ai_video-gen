"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Upload } from "lucide-react";
import { api, ApiError, assetUrl } from "@/lib/api/client";
import type { TalkJob, TalkLanguage, Voice } from "@/types/api";

const LANGUAGES: { id: TalkLanguage; label: string; hint: string }[] = [
  { id: "en", label: "English", hint: "Hello, welcome to my channel." },
  { id: "hi", label: "Hindi", hint: "नमस्ते, मेरे चैनल में आपका स्वागत है।" },
  { id: "ur", label: "Urdu", hint: "Assalam o alaikum, mere channel mein khush aamdeed." },
];

const STEP: Record<TalkJob["status"], string> = {
  queued: "Waiting for the GPU…",
  speaking: "Making the voice (Chatterbox)…",
  lip_syncing: "Moving the lips to the voice (MuseTalk). This takes a few minutes…",
  completed: "Done",
  failed: "Failed",
};

/** Adds speech and lip-sync to a finished video: text → voice (Chatterbox) → lips (MuseTalk). */
export function TalkingPanel({ sourceJobId }: { sourceJobId: string }) {
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<TalkLanguage>("en");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [job, setJob] = useState<TalkJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A missing voice list must not look like a failed job: the built-in voice still works.
  const [voicesNote, setVoicesNote] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [voiceName, setVoiceName] = useState("");
  const [gender, setGender] = useState<"male" | "female">("female");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .voices()
      .then(setVoices)
      .catch(() => setVoicesNote("Your saved voices could not be loaded right now; the built-in voice still works."));
  }, []);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const timer = setTimeout(() => {
      api.getTalk(job.id).then(setJob).catch(() => undefined);
    }, 2000);
    return () => clearTimeout(timer);
  }, [job]);

  const start = async () => {
    setError(null);
    if (!text.trim()) {
      setError("Write what the person should say.");
      return;
    }
    try {
      setJob(
        await api.createTalk({
          text: text.trim(),
          language,
          source_job_id: sourceJobId,
          ...(voiceId ? { voice_id: voiceId } : {}),
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start.");
    }
  };

  const addVoice = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !voiceName.trim()) {
      setError("Choose a recording and give the voice a name.");
      return;
    }
    setAdding(true);
    setError(null);
    try {
      const v = await api.addVoice(file, voiceName.trim(), gender);
      setVoices((list) => [...list, v]);
      setVoiceId(v.id);
      setVoiceName("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The recording could not be added.");
    } finally {
      setAdding(false);
    }
  };

  const busy = job !== null && job.status !== "completed" && job.status !== "failed";
  const src = job?.video_url ? assetUrl(job.video_url) : null;
  const field = "rounded-md border border-line bg-ink-950 px-2 py-1.5 text-fg";

  return (
    <div className="mt-3 rounded-lg border border-line bg-ink-900 p-3 text-xs text-fg-muted">
      <p className="mb-2 flex items-center gap-1.5 font-medium text-fg">
        <Mic className="size-3.5 text-violet-soft" aria-hidden />
        Make it talk · voice + lip-sync
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={600}
        rows={3}
        aria-label="What the person says"
        placeholder={LANGUAGES.find((l) => l.id === language)!.hint}
        className="w-full rounded-md border border-line bg-ink-950 p-2 text-sm text-fg"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <select value={language} onChange={(e) => setLanguage(e.target.value as TalkLanguage)} aria-label="Language" className={field}>
          {LANGUAGES.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </select>
        <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} aria-label="Voice" className={`min-w-0 flex-1 ${field}`}>
          <option value="">Built-in voice</option>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.gender})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void start()}
          disabled={busy}
          className="rounded-md bg-violet-500 px-3 py-1.5 font-medium text-white disabled:opacity-60"
        >
          {busy ? "Working…" : "Make it talk"}
        </button>
      </div>
      {language === "ur" && (
        <p className="mt-1.5 text-fg-subtle">Urdu is spoken by the Hindi voice model. Write it in Roman letters or Hindi script.</p>
      )}
      <details className="mt-2">
        <summary className="cursor-pointer text-fg-subtle">Add a voice from a recording (10–20 s, one person, no music)</summary>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" accept="audio/*" aria-label="Voice recording" className="max-w-full text-fg" />
          <input value={voiceName} onChange={(e) => setVoiceName(e.target.value)} placeholder="Name, e.g. Ali" aria-label="Voice name" className={field} />
          <select value={gender} onChange={(e) => setGender(e.target.value as "male" | "female")} aria-label="Gender" className={field}>
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
          <button
            type="button"
            onClick={() => void addVoice()}
            disabled={adding}
            className="flex items-center gap-1 rounded-md border border-line px-2 py-1.5 text-fg disabled:opacity-60"
          >
            <Upload className="size-3" aria-hidden /> {adding ? "Adding…" : "Add voice"}
          </button>
        </div>
        <p className="mt-1 text-fg-subtle">Use only recordings of people who agreed to have their voice copied.</p>
      </details>
      {voicesNote && <p className="mt-1.5 text-fg-subtle">{voicesNote}</p>}
      {job && (
        <p role="status" className="mt-2">
          {STEP[job.status]}
          {job.audio_seconds ? ` · ${job.audio_seconds}s of speech` : ""}
          {job.status === "failed" && job.error ? `: ${job.error}` : ""}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-300">
          {error}
        </p>
      )}
      {src && (
        <div className="mt-2">
          <video src={src} controls className="w-full rounded-md" />
          <a href={`${src}?download=true`} className="mt-1 inline-block text-violet-soft underline">
            Download MP4 with sound
          </a>
        </div>
      )}
    </div>
  );
}
