/* PathPilot — roadmap hexagon dial + side panel */
(function () {
	const wrap = document.getElementById("hexWrap");
	const panel = document.getElementById("rmPanel");
	if (!wrap || !panel) return;

	const el = {
		ico: document.getElementById("rmpIco"),
		name: document.getElementById("rmpName"),
		tag: document.getElementById("rmpTag"),
		diff: document.getElementById("rmpDiff"),
		weeks: document.getElementById("rmpWeeks"),
		ms: document.getElementById("rmpMs"),
		pct: document.getElementById("rmpPct"),
		bar: document.getElementById("rmpBar"),
		badge: document.getElementById("rmpBadge"),
		open: document.getElementById("rmpOpen"),
		activate: document.getElementById("rmpActivate"),
	};

	function paint(d) {
		panel.style.setProperty("--seg", d.accent);
		el.ico.innerHTML = `<i data-lucide="${d.icon}"></i>`;
		el.name.textContent = d.name;
		el.tag.textContent = d.tagline;
		el.diff.textContent = d.diff;
		el.diff.className = "chip diff-" + d.diff;
		el.weeks.textContent = d.weeks;
		el.ms.textContent = d.ms;
		el.pct.textContent = d.percent + "%";
		el.bar.style.width = d.percent + "%";
		el.open.setAttribute("href", d.href);
		const isActive = String(d.active) === "1";
		el.badge.style.display = isActive ? "" : "none";
		el.activate.hidden = isActive;
		el.activate.dataset.rid = d.id;
		if (window.refreshIcons) window.refreshIcons();
	}

	function fromWedge(w) {
		return {
			id: w.dataset.id,
			name: w.dataset.name,
			tagline: w.dataset.tagline,
			diff: w.dataset.diff,
			weeks: w.dataset.weeks,
			ms: w.dataset.ms,
			percent: w.dataset.percent,
			accent: w.dataset.accent,
			icon: w.dataset.icon,
			href: w.dataset.href,
			active: w.dataset.active ? "1" : "0",
		};
	}

	const wedges = wrap.querySelectorAll(".wedge[data-id]");
	wedges.forEach((w) => {
		const enter = () => paint(fromWedge(w));
		w.addEventListener("mouseenter", enter);
		w.addEventListener("focus", enter);
		w.addEventListener("click", () => {
			location.href = w.dataset.href;
		});
		w.addEventListener("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				location.href = w.dataset.href;
			}
		});
	});

	wrap.addEventListener("mouseleave", () => paint(window.__activeDefault));

	el.activate.addEventListener("click", async () => {
		const rid = el.activate.dataset.rid;
		await api("/roadmap/" + rid + "/activate", "POST");
		if (window.toast) toast("Roadmap activated");
		setTimeout(() => (location.href = "/"), 500);
	});

	paint(window.__activeDefault);
})();
