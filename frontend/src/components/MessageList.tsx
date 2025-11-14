type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { display_name: string }[];
};

type Props = {
  messages: Message[];
};

export default function MessageList({ messages }: Props) {
  return (
    <div className="message-list">
      {messages.map((msg) => (
        <article key={msg.id} className={`message ${msg.role}`}>
          <div className="bubble">
            <p>{msg.content}</p>
            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                <strong>출처</strong>
                <ul>
                  {msg.sources.map((src) => (
                    <li key={src.display_name}>{src.display_name}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
