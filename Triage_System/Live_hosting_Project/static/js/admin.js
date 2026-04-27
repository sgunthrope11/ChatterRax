const STATUS_OPTIONS = ["Open", "In Progress", "Resolved", "Closed"];

function setLastUpdatedState(message, tone = "idle") {
    const badgeColorMap = {
        idle: "bg-slate-400",
        success: "bg-emerald-500",
        error: "bg-rose-500"
    };
    const badgeColor = badgeColorMap[tone] || badgeColorMap.idle;

    document.getElementById("last-updated").innerHTML =
        `<span class="h-2 w-2 rounded-full ${badgeColor}"></span><span>${esc(message)}</span>`;
}

function resetStats() {
    document.getElementById("count-total").textContent = "0";
    document.getElementById("count-total-hero").textContent = "0 active";
    document.getElementById("count-high").textContent = "0";
    document.getElementById("count-medium").textContent = "0";
    document.getElementById("count-low").textContent = "0";
}

async function loadTickets() {
    const tbody = document.getElementById("ticket-tbody");
    tbody.innerHTML = '<tr class="state-row"><td colspan="7"><span class="spinner"></span>Loading tickets...</td></tr>';
    setLastUpdatedState("Refreshing queue...", "idle");

    try {
        const response = await fetch("/tickets");
        const payload = await response.json();

        if (!response.ok || payload.error) {
            throw new Error(payload.message || `Server responded ${response.status}`);
        }

        const tickets = payload.tickets || [];
        renderTable(tickets);
        updateStats(tickets);
        setLastUpdatedState(`Last updated: ${new Date().toLocaleTimeString()}`, "success");
    } catch (error) {
        resetStats();
        tbody.innerHTML = `<tr class="state-row"><td colspan="7">Failed to load tickets: ${esc(error.message)}</td></tr>`;
        setLastUpdatedState("Unable to refresh queue", "error");
    }
}

function renderTable(tickets) {
    const tbody = document.getElementById("ticket-tbody");

    if (!tickets.length) {
        tbody.innerHTML = '<tr class="state-row"><td colspan="7">No open tickets found.</td></tr>';
        return;
    }

    tbody.innerHTML = tickets.map(ticket => {
        const priority = (ticket.Priority || "").toLowerCase();
        const statusClass = ticket.Status ? ticket.Status.toLowerCase().replace(/\s+/g, "-") : "open";
        const options = STATUS_OPTIONS.map(status =>
            `<option value="${status}" ${status === ticket.Status ? "selected" : ""}>${status}</option>`
        ).join("");

        return `
        <tr id="row-${ticket.TicketID}">
          <td><span class="ticket-id">#${ticket.TicketID}</span></td>
          <td><div class="user-name">${esc(ticket.UserName)}</div></td>
          <td><span class="department">${esc(ticket.Department || "Not provided")}</span></td>
          <td><span class="priority-badge ${priority}">${esc(ticket.Priority)}</span></td>
          <td><div class="desc-cell" title="${esc(ticket.Description)}">${esc(ticket.Description)}</div></td>
          <td><span class="status-badge ${statusClass}">${esc(ticket.Status)}</span></td>
          <td>
            <div class="actions-cell">
              <select class="status-select" id="sel-${ticket.TicketID}">${options}</select>
              <button class="update-btn" onclick="updateTicket(${ticket.TicketID})">Update</button>
            </div>
          </td>
        </tr>`;
    }).join("");
}

async function updateTicket(ticketId) {
    const select = document.getElementById(`sel-${ticketId}`);
    if (!select) {
        showAlert(`Could not find ticket #${ticketId} in the table.`, "error");
        return;
    }
    const actionsCell = select.closest(".actions-cell");
    const button = actionsCell ? actionsCell.querySelector(".update-btn") : null;
    if (!button) {
        showAlert("Could not find the update button for this ticket.", "error");
        return;
    }
    const newStatus = select.value;

    button.disabled = true;
    button.textContent = "Saving...";

    try {
        const response = await fetch("/tickets/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ticket_id: ticketId, status: newStatus })
        });

        const payload = await response.json();

        if (!response.ok || payload.error) {
            throw new Error(payload.message || "Unable to update ticket.");
        }

        showAlert(payload.message || `Ticket #${ticketId} updated.`, "success");
        await loadTickets();
    } catch (error) {
        showAlert(`Update failed: ${error.message}`, "error");
        button.disabled = false;
        button.textContent = "Update";
    }
}

function updateStats(tickets) {
    const total = tickets.length;
    document.getElementById("count-total").textContent = total;
    document.getElementById("count-total-hero").textContent = `${total} active`;
    document.getElementById("count-high").textContent = tickets.filter(ticket => (ticket.Priority || "").toLowerCase() === "high").length;
    document.getElementById("count-medium").textContent = tickets.filter(ticket => (ticket.Priority || "").toLowerCase() === "medium").length;
    document.getElementById("count-low").textContent = tickets.filter(ticket => (ticket.Priority || "").toLowerCase() === "low").length;
}

let alertTimer;
function showAlert(message, type) {
    const box = document.getElementById("alert-box");
    box.textContent = message;
    box.className = `mb-6 rounded-lg p-4 text-sm font-medium ${type === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-rose-50 text-rose-700 border border-rose-200"}`;
    box.style.display = "block";
    clearTimeout(alertTimer);
    alertTimer = setTimeout(() => {
        box.style.display = "none";
    }, 5000);
}

function esc(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

loadTickets();
