// ── Phase Manager ─────────────────────────────────────
const PHASES = ['prepare', 'plan', 'execute', 'report'];

const PhaseManager = {
    current: 'prepare',
    completed: new Set(),

    init() {
        // Nav click handlers
        document.querySelectorAll('.phase-nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const phase = item.dataset.phase;
                if (this.completed.has(phase) && phase !== this.current) {
                    this.goTo(phase, true);  // read-only revisit
                }
            });
        });
        this.render();
    },

    goTo(phase, readOnly) {
        if (!PHASES.includes(phase)) return;

        // 把当前 phase 标记为已完成（无论前进还是后退）
        this.completed.add(this.current);

        this.current = phase;
        this.render();

        // Show/hide sections with animation
        document.querySelectorAll('.phase-section').forEach(sec => {
            sec.classList.remove('active');
        });
        const target = document.getElementById('phase-' + phase);
        // Force reflow for animation
        void target.offsetWidth;
        target.classList.add('active');
    },

    render() {
        const navItems = document.querySelectorAll('.phase-nav-item');
        const navLines = document.querySelectorAll('.phase-nav-line');

        navItems.forEach(item => {
            const phase = item.dataset.phase;
            item.classList.remove('active', 'completed', 'clickable');

            if (phase === this.current) {
                item.classList.add('active');
            } else if (this.completed.has(phase)) {
                item.classList.add('completed', 'clickable');
            }
        });

        navLines.forEach(line => {
            const idx = parseInt(line.dataset.line);
            line.classList.remove('completed');
            // Line is completed if the phase AFTER it is completed or is current and not the first
            const phaseAfter = PHASES[idx + 1];
            if (this.completed.has(PHASES[idx]) &&
                (this.completed.has(phaseAfter) || this.current === phaseAfter)) {
                line.classList.add('completed');
            }
        });
    },

    reset() {
        this.completed.clear();
        this.current = 'prepare';
        this.render();
        document.querySelectorAll('.phase-section').forEach(sec => {
            sec.classList.remove('active');
        });
        document.getElementById('phase-prepare').classList.add('active');
    }
};
