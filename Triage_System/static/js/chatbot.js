const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
let isSending = false;

function addMessage(text, sender) {
    const msg = document.createElement("div");
    msg.classList.add("message");
    msg.classList.add(sender === "user" ? "user-message" : "bot-message");
    msg.textContent = text;
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isSending) {
        return;
    }

    isSending = true;
    sendBtn.disabled = true;
    userInput.disabled = true;

    addMessage(message, "user");
    userInput.value = "";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message, user_id: 1 })
        });

        const data = await response.json();
        if (!response.ok || data.error) {
            throw new Error(data.reply || "Something went wrong. Please try again.");
        }

        addMessage(data.reply || "Something went wrong. Please try again.", "bot");

        if (!data.resolved && data.ticket_id) {
            addMessage(`Ticket #${data.ticket_id} has been created for the admin team.`, "bot");
        }
    } catch (error) {
        addMessage(error.message || "Something went wrong. Please try again.", "bot");
    } finally {
        isSending = false;
        sendBtn.disabled = false;
        userInput.disabled = false;
        userInput.focus();
    }
}

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        sendMessage();
    }
});
