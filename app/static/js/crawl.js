const box = document.querySelector("[data-job-url]");

function renderErrors(list, errors) {
  list.replaceChildren(...errors.map((error) => {
    const item = document.createElement("li");
    item.textContent = error.url ? `${error.url}: ${error.message}` : error.message;
    return item;
  }));
}

async function poll() {
  const progress = box.querySelector("progress");
  const status = box.querySelector(".progress__status");
  let job;
  try {
    const response = await fetch(box.dataset.jobUrl, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(String(response.status));
    job = await response.json();
  } catch {
    status.textContent = "Không đọc được tiến độ. Tải lại trang để xem kết quả.";
    return;
  }
  progress.max = job.total || 1;
  progress.value = job.done + job.failed;
  status.textContent = job.summary;
  renderErrors(box.querySelector(".progress__errors"), job.errors);
  if (job.active) {
    setTimeout(poll, 1000);
  } else {
    window.location.reload();
  }
}

if (box && box.dataset.active === "true") {
  poll();
}
