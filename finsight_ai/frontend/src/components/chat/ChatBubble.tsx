import { motion } from "framer-motion";
import { userBubbleVariants, assistantBubbleVariants } from "../../design/motion";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
}

export function ChatBubble({ role, content }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <motion.div
        variants={userBubbleVariants}
        initial="hidden"
        animate="visible"
        className="flex justify-end"
      >
        <div
          className="max-w-lg px-4 py-3 rounded-3xl rounded-br-lg text-white text-sm leading-relaxed"
          style={{
            background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
            boxShadow: "0 4px 20px rgba(255,122,90,0.25)",
          }}
        >
          {content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      variants={assistantBubbleVariants}
      initial="hidden"
      animate="visible"
      className="flex justify-start"
    >
      <div
        className="max-w-2xl px-4 py-3 rounded-3xl rounded-bl-lg text-sm text-ocean-deep leading-relaxed"
        style={{
          background: "rgba(255,255,255,0.88)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid rgba(205,237,246,0.8)",
          boxShadow: "0 4px 20px rgba(11,60,93,0.10)",
        }}
      >
        {content}
      </div>
    </motion.div>
  );
}
