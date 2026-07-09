/* PathPilot — statistics tabs + charts */
(function () {
	const D = JSON.parse(document.getElementById("statData").textContent);
	const css = getComputedStyle(document.documentElement);
	const accent = css.getPropertyValue("--accent").trim() || "#4f46e5";
	const accent2 = css.getPropertyValue("--accent-2").trim() || "#6366f1";
	const ink3 = css.getPropertyValue("--ink-3").trim() || "#6b7280";
	const grid = css.getPropertyValue("--border").trim() || "rgba(0,0,0,.07)";
	const surface2 = css.getPropertyValue("--surface-2").trim() || "#f2f4fa";

	Chart.defaults.font.family = "Inter, system-ui, sans-serif";
	Chart.defaults.color = ink3;
	Chart.defaults.font.size = 12;

	const built = {};

	function gradient(ctx, area, c1, c2) {
		const g = ctx.createLinearGradient(0, area.bottom, 0, area.top);
		g.addColorStop(0, c1);
		g.addColorStop(1, c2);
		return g;
	}

	const builders = {
		overview() {
			new Chart(document.getElementById("msChart"), {
				type: "bar",
				data: {
					labels: D.milestones.map((t) =>
						t.length > 16 ? t.slice(0, 15) + "…" : t,
					),
					datasets: [
						{
							data: D.milestonePercents,
							backgroundColor: (c) => {
								const { ctx, chartArea } = c.chart;
								if (!chartArea) return accent;
								return gradient(ctx, chartArea, accent, accent2);
							},
							borderRadius: 8,
							borderSkipped: false,
							maxBarThickness: 46,
						},
					],
				},
				options: baseOpts({ max: 100 }),
			});
		},
		study() {
			// hours by pillar (sum milestone hours per pillar)
			const map = {};
			D.milestonePillars.forEach((p, i) => {
				map[p] = (map[p] || 0) + D.milestoneHours[i];
			});
			new Chart(document.getElementById("studyChart"), {
				type: "bar",
				data: {
					labels: Object.keys(map),
					datasets: [
						{
							data: Object.values(map),
							backgroundColor: (c) => {
								const { ctx, chartArea } = c.chart;
								if (!chartArea) return accent;
								return gradient(ctx, chartArea, accent2, accent);
							},
							borderRadius: 8,
							borderSkipped: false,
							maxBarThickness: 60,
						},
					],
				},
				options: baseOpts({ suffix: "h" }),
			});
		},
		projects() {
			const s = D.projectStatus;
			new Chart(document.getElementById("projChart"), {
				type: "doughnut",
				data: {
					labels: ["Backlog", "In progress", "Review", "Done"],
					datasets: [
						{
							data: [s.backlog, s.in_progress, s.review, s.done],
							backgroundColor: ["#9aa1b1", "#f59e0b", accent, "#10b981"],
							borderWidth: 0,
							hoverOffset: 8,
						},
					],
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					cutout: "64%",
					plugins: {
						legend: {
							position: "bottom",
							labels: {
								padding: 16,
								usePointStyle: true,
								pointStyle: "circle",
							},
						},
					},
				},
			});
		},
		roadmaps() {
			new Chart(document.getElementById("rmChart"), {
				type: "bar",
				data: {
					labels: D.roadmapNames,
					datasets: [
						{
							data: D.roadmapPercents,
							backgroundColor: (c) => {
								const { ctx, chartArea } = c.chart;
								if (!chartArea) return accent;
								return gradient(ctx, chartArea, accent, accent2);
							},
							borderRadius: 8,
							borderSkipped: false,
							maxBarThickness: 50,
						},
					],
				},
				options: baseOpts({ max: 100, horizontal: true }),
			});
		},
	};

	function baseOpts({ max, suffix = "%", horizontal = false } = {}) {
		return {
			indexAxis: horizontal ? "y" : "x",
			responsive: true,
			maintainAspectRatio: false,
			plugins: {
				legend: { display: false },
				tooltip: { callbacks: { label: (c) => ` ${c.raw}${suffix}` } },
			},
			scales: {
				x: {
					grid: { color: grid, display: !horizontal },
					border: { display: false },
					max: horizontal ? max : undefined,
					ticks: { callback: (v) => (horizontal ? v + suffix : undefined) },
				},
				y: {
					grid: { color: grid, display: horizontal },
					border: { display: false },
					max: horizontal ? undefined : max,
					beginAtZero: true,
					ticks: {
						callback: (v) =>
							horizontal ? undefined : v + (suffix === "%" ? "" : suffix),
					},
				},
			},
		};
	}

	function activate(name) {
		document
			.querySelectorAll(".tab")
			.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
		document
			.querySelectorAll(".tab-panel")
			.forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
		if (builders[name] && !built[name]) {
			built[name] = true;
			setTimeout(() => builders[name](), 30);
		}
		if (window.animateRings) window.animateRings();
	}

	document
		.querySelectorAll(".tab")
		.forEach((t) => t.addEventListener("click", () => activate(t.dataset.tab)));
	activate("overview");
})();
