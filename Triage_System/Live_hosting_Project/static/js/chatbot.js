const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const profileNameInput = document.getElementById("profile-name");
const profileEmailInput = document.getElementById("profile-email");
const profileDepartmentInput = document.getElementById("profile-department");
const profileForm = document.getElementById("profile-form");
const profileSubmitBtn = document.getElementById("profile-submit-btn");
const profileSubmitStatus = document.getElementById("profile-submit-status");
const intakePanel = document.getElementById("intake-panel");
const chatPanel = document.getElementById("chat-panel");
const welcomeMessage = document.getElementById("chat-welcome-message");
const PROFILE_STORAGE_KEY = "chatterrax-user-profile";
const CHAT_CLIENT_ID_STORAGE_KEY = "chatterrax-chat-client-id";
const BOT_RESPONSE_DELAY_MS = 900;
const DOMAIN_CONFIG = window.CHATTERRAX_DOMAIN_CONFIG || {};

let isSending = false;
let profileSubmitted = false;


function buildWelcomeMessage(profile = {}) {
    const providedName = String(profile.name || "").trim();
    const introName = providedName ? ` ${providedName},` : " there,";
    const template = String(
        DOMAIN_CONFIG.welcome_template ||
        "Hi{name_part} I am ChatterRax, a support bot here to help you out."
    );
    return template.replace("{name_part}", introName);
}


function renderWelcomeMessage(profile = {}) {
    if (!welcomeMessage) {
        return;
    }
    welcomeMessage.textContent = buildWelcomeMessage(profile);
    if (userInput && DOMAIN_CONFIG.input_placeholder) {
        userInput.placeholder = DOMAIN_CONFIG.input_placeholder;
    }
}


function buildQuickActionPrompt(label) {
    const trimmed = String(label || "").trim();
    const template = String(DOMAIN_CONFIG.quick_action_template || "{label}");
    return trimmed ? template.replace("{label}", trimmed) : "";
}


function getOrCreateClientSessionId() {
    let clientId = sessionStorage.getItem(CHAT_CLIENT_ID_STORAGE_KEY);
    if (clientId) {
        return clientId;
    }

    clientId = window.crypto && typeof window.crypto.randomUUID === "function"
        ? window.crypto.randomUUID()
        : `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    sessionStorage.setItem(CHAT_CLIENT_ID_STORAGE_KEY, clientId);
    return clientId;
}


function createMessageElement(text, sender, options = {}) {
    const msg = document.createElement("div");
    msg.className = sender === "user" ? "chat-msg-user" : "chat-msg-bot";
    if (sender === "bot") {
        appendFormattedText(msg, text);

        if (Array.isArray(options.quickReplies) && options.quickReplies.length) {
            const actionList = document.createElement("div");
            actionList.className = "chat-quick-actions";

            options.quickReplies.forEach(label => {
                const prompt = buildQuickActionPrompt(label);
                if (!prompt) {
                    return;
                }

                const button = document.createElement("button");
                button.type = "button";
                button.className = "chat-quick-action";
                button.textContent = `Next: ${label}`;
                button.addEventListener("click", function() {
                    if (isSending) {
                        return;
                    }
                    userInput.value = prompt;
                    sendMessage();
                });
                actionList.appendChild(button);
            });

            if (actionList.childNodes.length) {
                msg.appendChild(actionList);
            }
        }
    } else {
        msg.textContent = text;
    }
    return msg;
}


function appendFormattedText(container, text, linkClass = "chat-link") {
    const urlPattern = /(https?:\/\/[^\s]+)/g;
    const parts = String(text || "").split(urlPattern);

    parts.forEach(part => {
        if (!part) {
            return;
        }

        if (/^https?:\/\//.test(part)) {
            const link = document.createElement("a");
            link.href = part;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.className = linkClass;
            link.textContent = part;
            container.appendChild(link);
            return;
        }

        container.appendChild(document.createTextNode(part));
    });
}


function addMessage(text, sender, options = {}) {
    const msg = createMessageElement(text, sender, options);
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
    return msg;
}


function addTypingBubble() {
    const bubble = document.createElement("div");
    bubble.className = "chat-typing-bubble";
    bubble.setAttribute("aria-live", "polite");
    bubble.innerHTML = `
        <div class="chat-typing-dots">
            <span></span><span></span><span></span>
        </div>
    `;
    chatBox.appendChild(bubble);
    chatBox.scrollTop = chatBox.scrollHeight;
    return bubble;
}


function removeTypingBubble(bubble) {
    if (bubble && bubble.parentNode) {
        bubble.parentNode.removeChild(bubble);
    }
}


function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}


function readUserProfile() {
    return {
        name: profileNameInput.value.trim(),
        email: profileEmailInput.value.trim(),
        department: profileDepartmentInput.value.trim()
    };
}


function saveUserProfile(profile) {
    sessionStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
}


function setChatAvailability(isAvailable) {
    userInput.disabled = !isAvailable || isSending;
    sendBtn.disabled = !isAvailable || isSending;

    if (userInput.disabled) {
        userInput.classList.add("bg-slate-100", "text-slate-400", "cursor-not-allowed");
    } else {
        userInput.classList.remove("bg-slate-100", "text-slate-400", "cursor-not-allowed");
    }
}


function updateScreenState() {
    intakePanel.classList.toggle("hidden", profileSubmitted);
    chatPanel.classList.toggle("hidden", !profileSubmitted);
}


function setProfileSubmittedState(isSubmitted, statusMessage) {
    profileSubmitted = isSubmitted;
    profileSubmitBtn.textContent = isSubmitted ? "Details Saved" : "Start Chat";
    profileSubmitBtn.disabled = isSubmitted;
    profileSubmitStatus.textContent = statusMessage;
    profileSubmitStatus.className = isSubmitted
        ? "text-xs text-center text-emerald-600 mt-4"
        : "text-xs text-center text-slate-400 mt-4";
    setChatAvailability(isSubmitted);
    updateScreenState();
}


function loadSavedProfile() {
    try {
        getOrCreateClientSessionId();
        const saved = sessionStorage.getItem(PROFILE_STORAGE_KEY);
        if (!saved) {
            renderWelcomeMessage({});
            setProfileSubmittedState(false, "Your data is securely logged for internal follow-up.");
            return;
        }

        const profile = JSON.parse(saved);
        profileNameInput.value = profile.name || "";
        profileEmailInput.value = profile.email || "";
        profileDepartmentInput.value = profile.department || "";
        renderWelcomeMessage(profile);
        setProfileSubmittedState(true, "Details saved. Your support session is ready.");
    } catch (error) {
        sessionStorage.removeItem(PROFILE_STORAGE_KEY);
        renderWelcomeMessage({});
        setProfileSubmittedState(false, "Your data is securely logged for internal follow-up.");
    }
}


function getValidatedUserProfile() {
    const profile = readUserProfile();

    if (!profile.name || !profile.email || !profile.department) {
        profileSubmitStatus.textContent = "Please enter your name, work email, and department or team before starting the chat.";
        profileSubmitStatus.className = "text-xs text-center text-rose-600 mt-4";

        if (!profile.name) {
            profileNameInput.focus();
        } else if (!profile.email) {
            profileEmailInput.focus();
        } else {
            profileDepartmentInput.focus();
        }
        return null;
    }

    const emailLooksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email);
    if (!emailLooksValid) {
        profileSubmitStatus.textContent = "Please enter a valid work email address before starting the chat.";
        profileSubmitStatus.className = "text-xs text-center text-rose-600 mt-4";
        profileEmailInput.focus();
        return null;
    }

    saveUserProfile(profile);
    return profile;
}


function submitUserProfile() {
    const profile = getValidatedUserProfile();
    if (!profile) {
        return null;
    }

    renderWelcomeMessage(profile);
    setProfileSubmittedState(true, "Details saved. Your support session is ready.");
    userInput.focus();
    return profile;
}


function markProfileAsEdited() {
    if (!profileSubmitted) {
        return;
    }

    setProfileSubmittedState(false, "Your details changed. Submit them again before chatting.");
}


async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isSending) {
        return;
    }

    if (!profileSubmitted) {
        profileSubmitStatus.textContent = "Please submit your details before sending a message.";
        profileSubmitStatus.className = "text-xs text-center text-rose-600 mt-4";
        profileSubmitBtn.focus();
        return;
    }

    const userProfile = readUserProfile();
    const clientSessionId = getOrCreateClientSessionId();

    isSending = true;
    setChatAvailability(true);

    addMessage(message, "user");
    userInput.value = "";
    const typingBubble = addTypingBubble();
    const startedAt = Date.now();

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: message,
                user: userProfile,
                client_session_id: clientSessionId
            })
        });

        const data = await response.json();
        const elapsed = Date.now() - startedAt;
        const remainingDelay = Math.max(0, BOT_RESPONSE_DELAY_MS - elapsed);
        await wait(remainingDelay);
        removeTypingBubble(typingBubble);

        if (!response.ok || data.error) {
            throw new Error(data.reply || "Something went wrong. Please try again.");
        }

        let botReply = data.reply || "Something went wrong. Please try again.";
        if (!data.resolved && data.ticket_id) {
            botReply += ` Ticket #${data.ticket_id} has been created for the admin team.`;
        }
        addMessage(botReply, "bot", {
            quickReplies: data.next_issue_options || []
        });

    } catch (error) {
        const elapsed = Date.now() - startedAt;
        const remainingDelay = Math.max(0, BOT_RESPONSE_DELAY_MS - elapsed);
        await wait(remainingDelay);
        removeTypingBubble(typingBubble);
        addMessage(error.message || "Something went wrong. Please try again.", "bot");
    } finally {
        isSending = false;
        setChatAvailability(true);
        userInput.focus();
    }
}


loadSavedProfile();

profileForm.addEventListener("submit", function(event) {
    event.preventDefault();
    submitUserProfile();
});

profileNameInput.addEventListener("input", markProfileAsEdited);
profileEmailInput.addEventListener("input", markProfileAsEdited);
profileDepartmentInput.addEventListener("input", markProfileAsEdited);
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        sendMessage();
    }
});
