const API_BASE = "http://localhost:8000"; // we’ll replace with your deployed backend later

const q = document.getElementById("q");
const askBtn = document.getElementById("ask");
const statusEl = document.getElementById("status");
const timelineEl = document.getElementById("timeline");
const sourcesEl = document.getElementById("sources");
const answerEl = document.getElementById("answer");

const modal = document.getElementById("modal");
const modalTitle = document.getElementById("modalTitle");
const modalText = document.getElementById("modalText");
document.getElementById("closeModal").onclick = () => modal.classList.add("hidden");

function setStatus(msg){ statusEl.textContent = msg; }
function clearUI(){
  timelineEl.innerHTML = "";
  sourcesEl.innerHTML = "";
  answerEl.innerHTML = "No answer yet.";
}

askBtn.onclick = async () => {
  clearUI();
  setStatus("Backend not connected yet. Next step will set up the API.");
  timelineEl.innerHTML = `<li>✅ UI is working. Next: build backend API.</li>`;
};