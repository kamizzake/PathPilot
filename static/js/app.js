/* PathPilot — shared client runtime */
(function () {
	function icons() {
		if (window.lucide) lucide.createIcons();
	}
	icons();
	// re-run after any dynamic insert
	window.refreshIcons = icons;

	/* ---- theme ---- */
	const root = document.documentElement;
	const toggle = document.getElementById("themeToggle");
	function setTheme(t) {
		root.setAttribute("data-theme", t);
		if (toggle) {
			toggle.querySelector("span").textContent =
				t === "dark" ? "Light mode" : "Dark mode";
			toggle
				.querySelector("[data-lucide]")
				.setAttribute("data-lucide", t === "dark" ? "sun" : "moon");
			icons();
		}
	}
	if (toggle) {
		toggle.addEventListener("click", () => {
			const next =
				root.getAttribute("data-theme") === "dark" ? "light" : "dark";
			setTheme(next);
			// persist to profile is optional; keep it session-local via a cookie-free approach
			fetch("/api/theme", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ theme: next }),
			}).catch(() => {});
		});
		setTheme(root.getAttribute("data-theme") || "light");
	}

	/* ---- toast ---- */
	window.toast = function (msg, ok = true) {
		const wrap = document.getElementById("toastWrap");
		const el = document.createElement("div");
		el.className = "toast";
		el.innerHTML = `<i data-lucide="${ok ? "check-circle-2" : "alert-circle"}"></i><span>${msg}</span>`;
		wrap.appendChild(el);
		icons();
		setTimeout(() => {
			el.style.opacity = "0";
			el.style.transform = "translateY(10px)";
			el.style.transition = "all .3s";
		}, 2400);
		setTimeout(() => el.remove(), 2800);
	};

	/* ---- api helper ---- */
	window.api = async function (url, method = "GET", body) {
		const opts = { method, headers: { "Content-Type": "application/json" } };
		if (body) opts.body = JSON.stringify(body);
		const r = await fetch(url, opts);
		return r.json();
	};

	/* ---- animate progress rings on load ---- */
	window.animateRings = function () {
		document.querySelectorAll(".ring").forEach((ring) => {
			const val = ring.querySelector(".val");
			if (!val) return;
			const circ = parseFloat(
				getComputedStyle(ring).getPropertyValue("--circ"),
			);
			const p = parseFloat(ring.style.getPropertyValue("--p")) || 0;
			requestAnimationFrame(() => {
				val.style.strokeDashoffset = circ * (1 - p / 100);
			});
		});
	};
	window.animateRings();

	/* ---- animate bars on load ---- */
	document.querySelectorAll(".bar > span[data-w]").forEach((s) => {
		requestAnimationFrame(() => {
			s.style.width = s.dataset.w + "%";
		});
	});
})();
