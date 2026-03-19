interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
}

export function ChatBubble({ role, content }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-lg px-4 py-3 rounded-2xl rounded-br-md bg-gradient-to-br from-coral to-coral-light text-white text-sm leading-relaxed shadow-glow/20">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-2xl px-4 py-3 rounded-2xl rounded-bl-md bg-white border border-ocean-100 text-sm text-slate leading-relaxed shadow-soft">
        {content}
      </div>
    </div>
  );
}
