import { JournalApp } from "@/components/JournalApp";

export const dynamic = "force-dynamic";

export default function Home() {
  return <JournalApp showDesktopDownload={process.env.GENERAL_RAG_DESKTOP !== "1"} />;
}
