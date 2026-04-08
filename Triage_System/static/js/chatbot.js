const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const profileNameInput = document.getElementById("profile-name");
const profileEmailInput = document.getElementById("profile-email");
const profileDepartmentInput = document.getElementById("profile-department");
const profileSubmitBtn = document.getElementById("profile-submit-btn");
const profileSubmitStatus = document.getElementById("profile-submit-status");
const intakeScreen = document.getElementById("intake-screen");
const chatInterface = document.getElementById("chat-interface");
let isSending = false;
const PROFILE_STORAGE_KEY = "chatterrax-user-profile";
const BOT_RESPONSE_DELAY_MS = 12000;
let profileSubmitted = false;

function addMessage(text, sender) {
    const msg = document.createElement("div");
    msg.classList.add("message");
    msg.classList.add(sender === "user" ? "user-message" : "bot-message");
    msg.textContent = text;
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addTypingBubble() {
    const bubble = document.createElement("div");
    bubble.classList.add("message", "bot-message", "typing-message");
    bubble.setAttribute("aria-live", "polite");
    bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
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
}

function updateScreenState() {
    intakeScreen.classList.toggle("intake-screen-hidden", profileSubmitted);
    chatInterface.classList.toggle("chat-interface-hidden", !profileSubmitted);
}

function setProfileSubmittedState(isSubmitted, statusMessage) {
    profileSubmitted = isSubmitted;
    profileSubmitBtn.textContent = isSubmitted ? "Details Saved" : "Submit Details";
    profileSubmitBtn.disabled = isSubmitted;
    profileSubmitStatus.textContent = statusMessage;
    setChatAvailability(isSubmitted);
    updateScreenState();
}

function loadSavedProfile() {
    try {
        const saved = sessionStorage.getItem(PROFILE_STORAGE_KEY);
        if (!saved) {
            setProfileSubmittedState(false, "Submit your details before starting the chat.");
            return;
        }

        const profile = JSON.parse(saved);
        profileNameInput.value = profile.name || "";
        profileEmailInput.value = profile.email || "";
        profileDepartmentInput.value = profile.department || "";
        setProfileSubmittedState(true, "Details saved. You can start chatting.");
    } catch (error) {
        sessionStorage.removeItem(PROFILE_STORAGE_KEY);
        setProfileSubmittedState(false, "Submit your details before starting the chat.");
    }
}

function getValidatedUserProfile() {
    const profile = readUserProfile();

    if (!profile.name || !profile.email || !profile.department) {
        addMessage("Please enter your name, email, and department before sending a message.", "bot");
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
        addMessage("Please enter a valid email address before sending a message.", "bot");
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

    setProfileSubmittedState(true, "Details saved. You can start chatting.");
    userInput.focus();
    return profile;
}

function markProfileAsEdited() {
    if (!profileSubmitted) {
        return;
    }

    setProfileSubmittedState(false, "Your details changed. Please submit them again before chatting.");
}

async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isSending) {
        return;
    }

    if (!profileSubmitted) {
        addMessage("Please submit your name, email, and department before sending a message.", "bot");
        profileSubmitBtn.focus();
        return;
    }

    const userProfile = readUserProfile();

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
                user: userProfile
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
        addMessage(botReply, "bot");
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
profileSubmitBtn.addEventListener("click", submitUserProfile);
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
