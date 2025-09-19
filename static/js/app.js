// static/js/app.js
document.addEventListener('DOMContentLoaded', () => {
    // ... (your existing elements and fetchData function) ...

    const startTransferBtn = document.getElementById('start-transfer-btn');
    const transferModal = document.getElementById('transfer-modal');
    const closeBtn = document.querySelector('.close-btn');
    const recipientChecklist = document.getElementById('recipient-checklist');
    const fileInput = document.getElementById('file-input');
    const sendFilesBtn = document.getElementById('send-files-btn');

    // --- Event Listeners to open/close the modal ---
    startTransferBtn.addEventListener('click', openTransferModal);
    closeBtn.addEventListener('click', () => transferModal.style.display = 'none');

    async function openTransferModal() {
        // Step 1: Fetch the latest agent list from the server
        const response = await fetch('/api/agents');
        const agents = await response.json();

        // Step 2: Build the HTML for the checkbox list
        if (agents.length > 0) {
            recipientChecklist.innerHTML = `
                <label><input type="checkbox" id="select-all-agents"> Select All</label><hr>
            ` + agents.map(agent => `
                <div>
                    <label>
                        <input type="checkbox" class="agent-checkbox" value="${agent.agent_id}">
                        ${agent.agent_id}
                    </label>
                </div>
            `).join('');
        } else {
            recipientChecklist.innerHTML = "<p>No agents are currently connected.</p>";
        }

        // Step 3: Show the modal
        transferModal.style.display = 'block';
    }

    // Add event listener for the "Select All" checkbox
    recipientChecklist.addEventListener('change', (event) => {
        if (event.target.id === 'select-all-agents') {
            document.querySelectorAll('.agent-checkbox').forEach(cb => {
                cb.checked = event.target.checked;
            });
        }
    });

    // Handle the final "Send Files" button click
    sendFilesBtn.addEventListener('click', async () => {
        const selectedFiles = fileInput.files;
        const checkedBoxes = document.querySelectorAll('.agent-checkbox:checked');
        const recipientIds = Array.from(checkedBoxes).map(cb => cb.value);

        if (selectedFiles.length === 0 || recipientIds.length === 0) {
            alert("Please select at least one file and one recipient.");
            return;
        }

        const formData = new FormData();
        // Add all selected files to the form data
        for (const file of selectedFiles) {
            formData.append('files[]', file);
        }
        // Add all selected recipients
        for (const id of recipientIds) {
            formData.append('recipients', id);
        }

        // Send the data to the server
        const response = await fetch('/api/transfer/host-to-client', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        alert(result.message);
        transferModal.style.display = 'none'; // Close modal on success
    });

    // ... (your existing fetchData interval) ...
});