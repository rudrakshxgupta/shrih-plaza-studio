let currentDecision = "approved";
let lastResultPackage = null;

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setStatus(text, muted = false) {
  const pill = $("statusPill");
  pill.textContent = text;
  pill.classList.toggle("muted", muted);
}

function renderArchitectureChecklist(imageGeneration) {
  const container = $("architectureChecklist");
  if (!imageGeneration) {
    container.innerHTML = "";
    return;
  }

  const lastAttempt = (imageGeneration.attempts || []).at(-1);
  const verdict = lastAttempt && lastAttempt.verdict;

  if (imageGeneration.status === "needs_manual_checklist" && imageGeneration.checklist_items) {
    container.innerHTML = `
      <div class="checklist-panel">
        <p class="label">No Gemini key configured -- confirm this checklist by eye before approving.</p>
        ${imageGeneration.checklist_items.map((item) => `
          <label class="checklist-row">
            <input type="checkbox" class="checklist-check" data-key="${item.key}" checked />
            ${item.label}
          </label>
        `).join("")}
        <textarea id="checklistNotes" class="small-area" placeholder="Notes on anything that doesn't match"></textarea>
        <button id="confirmChecklistBtn" class="secondary-button" type="button">Submit Checklist</button>
        <p id="checklistStatus" class="hint"></p>
      </div>
    `;
    $("confirmChecklistBtn").addEventListener("click", submitArchitectureChecklist);
    return;
  }

  if (verdict && verdict.mode === "gemini_vision") {
    container.innerHTML = `
      <div class="checklist-panel">
        <p class="label">Architecture guard (Gemini vision): ${verdict.approved ? "APPROVED" : "REJECTED"}</p>
        ${Object.entries(verdict.checklist || {}).map(([key, value]) => `
          <div class="checklist-row"><span class="${value ? "pass" : "fail"}">${value ? "✓" : "✗"}</span> ${key.replace(/_/g, " ")}</div>
        `).join("")}
        ${(verdict.issues || []).length ? `<p class="hint">Issues: ${verdict.issues.join("; ")}</p>` : ""}
      </div>
    `;
    return;
  }

  if (imageGeneration.status === "unavailable" || imageGeneration.status === "failed") {
    container.innerHTML = `<div class="checklist-panel"><p class="hint">Image generation unavailable: ${imageGeneration.reason || imageGeneration.error || "unknown error"}</p></div>`;
    return;
  }

  container.innerHTML = "";
}

async function submitArchitectureChecklist() {
  const checklist = {};
  document.querySelectorAll(".checklist-check").forEach((box) => {
    checklist[box.dataset.key] = box.checked;
  });
  const approved = Object.values(checklist).every(Boolean);
  const notes = $("checklistNotes").value.trim();
  const result = await api("/api/architecture-confirm", {
    method: "POST",
    body: JSON.stringify({ approved, checklist, notes }),
  });
  $("checklistStatus").textContent = result.approved
    ? "Confirmed -- architecture preserved."
    : "Logged as a mistake. Future prompts will avoid this.";
}

function renderResult(result) {
  lastResultPackage = result;
  const content = result.final_content || {};
  $("resultStatus").textContent = result.status || "Complete";
  $("resultStatus").classList.toggle("muted", !String(result.status || "").startsWith("approved") && !String(result.status || "").includes("approved"));
  $("hook").textContent = content.hook || "";
  $("caption").textContent = content.caption || "";
  $("visual").textContent = content.visual_direction || "";
  $("hashtags").innerHTML = (content.hashtags || []).map((tag) => `<span class="chip">${tag}</span>`).join("");

  const rendered = result.rendered_image;
  if (rendered && rendered.output) {
    $("postPreview").src = `/api/file?path=${encodeURIComponent(rendered.output)}`;
    $("postPreview").style.display = "block";
    $("imagePath").textContent = rendered.output;
  } else {
    $("postPreview").style.display = "none";
    $("imagePath").textContent = "";
  }

  const imageGeneration = result.image_generation;
  const finalImage = imageGeneration && (imageGeneration.final_image || (imageGeneration.status === "approved" && imageGeneration.final_image));
  if (finalImage) {
    $("generatedImagePreview").src = `/api/file?path=${encodeURIComponent(finalImage)}`;
    $("generatedImagePreview").style.display = "block";
    $("generatedImageStatus").textContent = `${imageGeneration.status}`;
  } else {
    $("generatedImagePreview").style.display = "none";
    $("generatedImageStatus").textContent = imageGeneration ? imageGeneration.status : "";
  }
  renderArchitectureChecklist(imageGeneration);

  const latest = (result.review_history || []).at(-1);
  const reviews = latest ? latest.reviews || [] : [];
  $("reviews").innerHTML = reviews.map((review) => {
    const ok = review.approved ? "PASS" : "FIX";
    const cls = review.approved ? "pass" : "fail";
    return `
      <div class="review-row">
        <strong>${review.agent || "review"}</strong>
        <span class="score">${review.score ?? "-"}/10</span>
        <span class="${cls}">${ok}</span>
      </div>
    `;
  }).join("");
}

async function loadMemory() {
  const memory = await api("/api/memory");
  $("claims").innerHTML = (memory.project.approved_claims || [])
    .map((claim) => `<li>${claim}</li>`)
    .join("");
  $("brands").innerHTML = (memory.project.signed_brand_associations || [])
    .map((brand) => `<span class="chip">${brand}</span>`)
    .join("");
}

async function loadReferenceImages() {
  const data = await api("/api/reference-images");
  const select = $("referenceImage");
  const previous = select.value;
  select.innerHTML = '<option value="">None</option>' + (data.images || [])
    .map((image) => `<option value="${image.path}">${image.name}</option>`)
    .join("");
  if (previous) select.value = previous;
}

async function generate() {
  setStatus("Running", true);
  $("generateBtn").disabled = true;
  try {
    const result = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        brief: $("brief").value,
        platform: $("platform").value,
        format: $("format").value,
        generate_image: $("generateImageToggle").checked,
        reference_image: $("referenceImage").value || null,
      }),
    });
    renderResult(result);
    setStatus("Complete");
  } catch (error) {
    setStatus("Error", true);
    alert(error.message);
  } finally {
    $("generateBtn").disabled = false;
  }
}

async function saveFeedback() {
  const feedback = $("feedback").value.trim();
  if (!feedback) {
    $("feedbackStatus").textContent = "Write feedback first.";
    return;
  }

  if (currentDecision === "approved") {
    await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ decision: currentDecision, feedback }),
    });
    $("feedbackStatus").textContent = "Saved. The agent will use this preference next time.";
    $("feedback").value = "";
    return;
  }

  if (!lastResultPackage) {
    $("feedbackStatus").textContent = "Generate a draft first.";
    return;
  }

  $("feedbackStatus").textContent = "Regenerating with your feedback...";
  try {
    const result = await api("/api/regenerate", {
      method: "POST",
      body: JSON.stringify({
        decision: currentDecision,
        feedback,
        content: lastResultPackage.final_content,
        reference_image: $("referenceImage").value || null,
      }),
    });
    renderResult(result);
    $("feedbackStatus").textContent = `Regenerated -- status: ${result.status}`;
    $("feedback").value = "";
  } catch (error) {
    $("feedbackStatus").textContent = `Regeneration failed: ${error.message}`;
  }
}

async function enhanceImage(event) {
  event.preventDefault();
  const file = $("imageInput").files[0];
  if (!file) {
    $("imageStatus").textContent = "Choose an image first.";
    return;
  }
  const form = new FormData();
  form.append("image", file);
  $("imageStatus").textContent = "Enhancing safely...";
  const result = await api("/api/enhance-image", {
    method: "POST",
    body: form,
  });
  $("imageStatus").textContent = `Enhanced saved: ${result.enhanced}`;
}

async function uploadReferenceImage(event) {
  event.preventDefault();
  const file = $("referenceInput").files[0];
  if (!file) {
    $("referenceStatus").textContent = "Choose an image first.";
    return;
  }
  const form = new FormData();
  form.append("image", file);
  $("referenceStatus").textContent = "Uploading...";
  const result = await api("/api/upload-reference-image", {
    method: "POST",
    body: form,
  });
  $("referenceStatus").textContent = `Added: ${result.name}`;
  $("referenceInput").value = "";
  await loadReferenceImages();
}

document.addEventListener("DOMContentLoaded", () => {
  $("generateBtn").addEventListener("click", generate);
  $("refreshMemory").addEventListener("click", loadMemory);
  $("saveFeedback").addEventListener("click", saveFeedback);
  $("imageForm").addEventListener("submit", enhanceImage);
  $("referenceForm").addEventListener("submit", uploadReferenceImage);

  document.querySelectorAll(".choice").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".choice").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      currentDecision = button.dataset.decision;
    });
  });

  loadMemory();
  loadReferenceImages();
});
