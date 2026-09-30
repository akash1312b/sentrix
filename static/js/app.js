/**
 * Sentrix — Enterprise AI Inventory Intelligence Platform
 * Reactive Single-Page Application Controller & Audio Engine
 */

const App = {
    state: {
        currentTab: 'dashboard',
        shop: { id: '', name: '', currency: 'INR' },
        all_shops: [],
        metrics: {},
        products: [],
        categories: [],
        suppliers: [],
        purchase_orders: [],
        alerts: [],
        recent_transactions: [],
        chartsData: {},
        
        // POS Cart
        cart: [],
        posCategoryFilter: '',

        // Inventory filters & sorting
        searchQuery: '',
        categoryFilter: '',
        statusFilter: 'all',
        sortField: 'name',
        sortAsc: true,
        txFilter: 'all',

        // Modals & Chat
        selectedAdjustProduct: null,
        selectedAdjustType: 'sale_out',
        chatSessionId: null,
        soundEnabled: true,
    },

    charts: {
        trendChart: null,
        categoryChart: null,
    },

    /* ==========================================================================
       Authenticated API Fetch & Token Auto-Refresh
       ========================================================================== */
    async apiFetch(url, options = {}, isRetry = false) {
        const accessToken = localStorage.getItem('access_token');
        const shopId = localStorage.getItem('shop_id') || this.state.shop.id;

        const opts = { ...options };
        opts.headers = { ...(options.headers || {}) };

        if (accessToken && !opts.headers['Authorization']) {
            opts.headers['Authorization'] = `Bearer ${accessToken}`;
        }
        if (shopId && !opts.headers['X-Shop-Id']) {
            opts.headers['X-Shop-Id'] = shopId;
        }

        try {
            const response = await fetch(url, opts);

            if (response.status === 401) {
                if (!isRetry) {
                    const refreshToken = localStorage.getItem('refresh_token');
                    if (refreshToken) {
                        try {
                            const refreshRes = await fetch('/api/v1/auth/token/refresh/', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ refresh: refreshToken }),
                            });
                            if (refreshRes.ok) {
                                const refreshData = await refreshRes.json();
                                if (refreshData.access) {
                                    localStorage.setItem('access_token', refreshData.access);
                                    if (refreshData.refresh) {
                                        localStorage.setItem('refresh_token', refreshData.refresh);
                                    }
                                    const retryOpts = { ...options };
                                    retryOpts.headers = { ...(options.headers || {}) };
                                    retryOpts.headers['Authorization'] = `Bearer ${refreshData.access}`;
                                    if (shopId) retryOpts.headers['X-Shop-Id'] = shopId;
                                    return this.apiFetch(url, retryOpts, true);
                                }
                            }
                        } catch (refreshErr) {
                            console.error('Failed to refresh access token:', refreshErr);
                        }
                    }
                }
                // Refresh failed or no refresh token -> log out
                this.logout('Your session ended. Please log in again.');
                return response;
            }

            return response;
        } catch (err) {
            throw err;
        }
    },

    logout(message = '') {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('shop_id');
        localStorage.removeItem('shop_name');
        if (message) {
            sessionStorage.setItem('auth_message', message);
        }
        window.location.href = '/login/';
    },

    init() {
        // Protect dashboard: check if access token is present
        const token = localStorage.getItem('access_token');
        if (!token) {
            window.location.href = '/login/';
            return;
        }

        const savedShopId = localStorage.getItem('shop_id');
        const savedShopName = localStorage.getItem('shop_name');
        if (savedShopId) this.state.shop.id = savedShopId;
        if (savedShopName) this.state.shop.name = savedShopName;

        this.renderTopShopInfo();

        const page = document.body.getAttribute('data-page') || 'dashboard';
        this.state.currentTab = page;
        this.bindEvents();
        this.loadData();
        // Live poll every 25 seconds for background Celery tasks / other cashiers
        setInterval(() => this.loadData(true), 25000);
    },

    bindEvents() {
        // Tab routing (desktop sidebar, header, and mobile bottom bar)
        document.querySelectorAll('[data-tab]').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                const tab = el.getAttribute('data-tab');
                this.switchTab(tab);
            });
        });

        // Search inputs
        const prodSearch = document.getElementById('product-search-input');
        if (prodSearch) {
            prodSearch.addEventListener('input', (e) => {
                this.state.searchQuery = e.target.value;
                const clearBtn = document.getElementById('clear-search-btn');
                if (clearBtn) clearBtn.style.display = e.target.value ? 'block' : 'none';
                this.applyFilters();
            });
        }

        // Chat form submit
        const chatForm = document.getElementById('chat-fullscreen-form');
        if (chatForm) {
            chatForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleChatSubmit();
            });
        }

        // Global hotkeys (Ctrl+K / Cmd+K for Command Palette, F9 for POS Checkout, Esc for modals)
        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                this.openCommandPalette();
            }
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
            if (e.key === 'F9' && this.state.currentTab === 'pos') {
                e.preventDefault();
                this.submitPosCheckout();
            }
        });

        // Command Palette Input listener
        const cmdInput = document.getElementById('cmd-palette-input');
        if (cmdInput) {
            cmdInput.addEventListener('input', (e) => {
                this.renderCommandPaletteResults(e.target.value);
            });
            cmdInput.addEventListener('keydown', (e) => {
                this.handleCommandPaletteKeydown(e);
            });
        }
    },

    /* ==========================================================================
       Tab Navigation
       ========================================================================== */
    switchTab(tabName) {
        this.state.currentTab = tabName;

        // Update nav active states
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-tab') === tabName);
        });
        document.querySelectorAll('.bottom-tab').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-tab') === tabName);
        });

        // Switch view section visibility
        document.querySelectorAll('.view-section').forEach(sec => {
            sec.classList.remove('active');
        });
        const targetView = document.getElementById(`view-${tabName}`);
        if (targetView) {
            targetView.classList.add('active');
        }

        // Update top-bar titles
        const titles = {
            dashboard: { title: 'Shop Overview', sub: 'Today\'s sales, stock value, and fast billing' },
            inventory: { title: 'Products & Stock', sub: 'Check quantities, edit prices, or add new items' },
            pos: { title: 'Billing Counter (POS)', sub: 'Fast counter sales: click products or scan barcode to bill' },
            orders: { title: 'Supplier Orders', sub: 'Track your vendor orders and incoming restock deliveries' },
            alerts: { title: 'Stock Alerts & Warnings', sub: 'Notifications when products run low or finish' },
            chat: { title: 'Shop AI Assistant', sub: 'Your 24/7 digital helper for stock queries and quick sales' },
        };

        const titleEl = document.getElementById('current-view-title');
        const subEl = document.getElementById('current-view-subtitle');
        if (titleEl && titles[tabName]) titleEl.textContent = titles[tabName].title;
        if (subEl && titles[tabName]) subEl.textContent = titles[tabName].sub;

        // Re-render components specific to tab
        if (tabName === 'pos') {
            this.renderPosProducts();
        } else if (tabName === 'dashboard') {
            this.renderCharts();
        }

        // Close mobile sidebar if open
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.remove('open');

        window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    toggleMobileSidebar() {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.toggle('open');
    },

    /* ==========================================================================
       Audio Engine (Web Audio API Synthesizer)
       ========================================================================== */
    playSound(type = 'click') {
        if (!this.state.soundEnabled) return;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            const now = ctx.currentTime;
            if (type === 'beep') {
                // Barcode laser scan beep
                osc.type = 'sine';
                osc.frequency.setValueAtTime(1800, now);
                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
                osc.start(now);
                osc.stop(now + 0.08);
            } else if (type === 'chime') {
                // POS Checkout Success Chime
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(523.25, now); // C5
                osc.frequency.setValueAtTime(659.25, now + 0.08); // E5
                osc.frequency.setValueAtTime(783.99, now + 0.16); // G5
                osc.frequency.setValueAtTime(1046.50, now + 0.24); // C6
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
                osc.start(now);
                osc.stop(now + 0.45);
            } else if (type === 'error') {
                // Error buzz
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(140, now);
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
                osc.start(now);
                osc.stop(now + 0.2);
            }
        } catch (e) {
            // AudioContext not supported or allowed before user gesture
        }
    },

    toggleSound() {
        this.state.soundEnabled = !this.state.soundEnabled;
        const icon = document.getElementById('sound-icon');
        if (icon) icon.textContent = this.state.soundEnabled ? '🔊' : '🔇';
        this.showToast(this.state.soundEnabled ? 'Sound FX enabled' : 'Sound FX muted', 'info');
    },

    /* ==========================================================================
       Data Fetching & State Hydration
       ========================================================================== */
    async loadData(silent = false) {
        try {
            const savedShopId = localStorage.getItem('shop_id');
            const targetShopId = this.state.shop.id || savedShopId;
            const url = targetShopId 
                ? `/api/dashboard-data/?shop_id=${targetShopId}` 
                : '/api/dashboard-data/';
            
            const res = await this.apiFetch(url);
            if (!res.ok) throw new Error('Failed to fetch dashboard data');
            const data = await res.json();

            this.state.shop = data.shop || this.state.shop;
            if (data.shop && data.shop.name) {
                localStorage.setItem('shop_name', data.shop.name);
                if (data.shop.id) {
                    localStorage.setItem('shop_id', data.shop.id);
                }
            }
            this.state.all_shops = data.all_shops || [];
            this.state.metrics = data.metrics;
            this.state.products = data.products;
            this.state.categories = data.categories;
            this.state.suppliers = data.suppliers;
            this.state.purchase_orders = data.purchase_orders;
            this.state.alerts = data.alerts;
            this.state.recent_transactions = data.recent_transactions;
            this.state.chartsData = data.charts || {};

            this.renderTopShopInfo();
            this.renderMetrics();
            this.renderCharts();
            this.renderDashboardCriticalInventory();
            this.renderTransactions();
            this.applyFilters();
            this.populateSelectDropdowns();
            this.renderSuppliers();
            this.renderOrders();
            this.renderAlerts();
            this.renderPosProducts();
            this.checkSampleDataStatus();

        } catch (err) {
            if (!silent) this.showToast('Error syncing with backend', 'error');
            console.error(err);
        }
    },

    handleShopChange(shopId) {
        this.state.shop.id = shopId;
        localStorage.setItem('shop_id', shopId);
        const selectedShop = this.state.all_shops.find(s => s.id === shopId);
        if (selectedShop) {
            this.state.shop.name = selectedShop.name;
            localStorage.setItem('shop_name', selectedShop.name);
            this.renderTopShopInfo();
        }
        this.loadData();
    },

    renderTopShopInfo() {
        const savedShopName = localStorage.getItem('shop_name');
        const shopName = savedShopName || this.state.shop.name || 'Sentrix Shop';
        const cur = this.state.shop.currency || 'INR';
        document.querySelectorAll('.shop-name-display').forEach(el => el.textContent = shopName);
        document.querySelectorAll('.currency-label').forEach(el => el.textContent = cur);
        const curDisp = document.getElementById('sidebar-currency-display');
        if (curDisp) curDisp.textContent = cur;
    },

    renderMetrics() {
        const m = this.state.metrics || {};
        const cur = this.state.shop.currency || 'INR';

        this.setSafeText('kpi-valuation', `${cur} ${(m.total_valuation || 0).toLocaleString()}`);
        this.setSafeText('kpi-total-products', m.total_products || 0);
        this.setSafeText('kpi-low-stock', m.low_stock_count || 0);
        this.setSafeText('kpi-out-stock', m.out_of_stock_count || 0);
        this.setSafeText('sidebar-product-count', m.total_products || 0);

        // Sidebar Badges
        const alertBadge = document.getElementById('sidebar-alert-badge');
        if (alertBadge) {
            const count = m.active_alerts || 0;
            alertBadge.textContent = count;
            alertBadge.style.display = count > 0 ? 'inline-block' : 'none';
        }

        const orderBadge = document.getElementById('sidebar-order-badge');
        if (orderBadge) {
            const count = m.pending_orders || 0;
            orderBadge.textContent = count;
            orderBadge.style.display = count > 0 ? 'inline-block' : 'none';
        }

        const alertHeaderCount = document.getElementById('alerts-header-count');
        if (alertHeaderCount) {
            alertHeaderCount.textContent = `${m.active_alerts || 0} Active`;
        }
    },

    /* ==========================================================================
       Chart.js Visual Analytics Engine (Warm Orange & Neutral Grey Theme)
       ========================================================================== */
    renderCharts() {
        if (!window.Chart || !this.state.chartsData.trends) return;

        const trends = this.state.chartsData.trends;
        const cats = this.state.chartsData.categories;

        // 1. Trend Line/Bar Chart (Warm Orange for Sales, Dark Slate for Restock)
        const trendCanvas = document.getElementById('trendChart');
        if (trendCanvas) {
            if (this.charts.trendChart) this.charts.trendChart.destroy();
            const ctx = trendCanvas.getContext('2d');
            this.charts.trendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trends.labels,
                    datasets: [
                        {
                            label: 'Sales Out',
                            data: trends.sales,
                            borderColor: '#DC2626',
                            backgroundColor: 'rgba(220, 38, 38, 0.08)',
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5,
                            pointBackgroundColor: '#DC2626',
                            pointRadius: 4,
                        },
                        {
                            label: 'Restock In',
                            data: trends.restock,
                            borderColor: '#9CA3AF',
                            backgroundColor: 'rgba(156, 163, 175, 0.08)',
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2,
                            pointBackgroundColor: '#9CA3AF',
                            pointRadius: 4,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: '#2D2D2D', font: { family: 'Inter', size: 12, weight: '600' } } },
                        tooltip: { backgroundColor: '#FFFFFF', titleColor: '#2D2D2D', bodyColor: '#666666', borderColor: '#EFE8DE', borderWidth: 1 }
                    },
                    scales: {
                        x: { grid: { color: '#EFE8DE' }, ticks: { color: '#666666' } },
                        y: { grid: { color: '#EFE8DE' }, ticks: { color: '#666666' } }
                    }
                }
            });
        }

        // 2. Category Share Doughnut
        const catCanvas = document.getElementById('categoryChart');
        if (catCanvas && cats) {
            if (this.charts.categoryChart) this.charts.categoryChart.destroy();
            const ctx = catCanvas.getContext('2d');
            this.charts.categoryChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: cats.labels.length ? cats.labels : ['Empty'],
                    datasets: [{
                        data: cats.values.length ? cats.values : [1],
                        backgroundColor: ['#E8873D', '#D9772F', '#F59E0B', '#78716C', '#57534E', '#A8A29E'],
                        borderColor: '#FFFFFF',
                        borderWidth: 2,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { color: '#2D2D2D', font: { family: 'Inter', size: 11, weight: '500' } } },
                        tooltip: { backgroundColor: '#FFFFFF', titleColor: '#2D2D2D', bodyColor: '#666666', borderColor: '#EFE8DE', borderWidth: 1 }
                    },
                    cutout: '68%'
                }
            });
        }
    },

    /* ==========================================================================
       Dashboard Critical Monitor & Audit Ledger
       ========================================================================== */
    renderDashboardCriticalInventory() {
        const tbody = document.getElementById('dashboard-inventory-table-body');
        if (!tbody) return;

        // Show out-of-stock first, then low stock, then top items
        const critical = [...this.state.products].sort((a, b) => {
            if (a.is_out_of_stock && !b.is_out_of_stock) return -1;
            if (!a.is_out_of_stock && b.is_out_of_stock) return 1;
            if (a.is_low_stock && !b.is_low_stock) return -1;
            if (!a.is_low_stock && b.is_low_stock) return 1;
            return a.quantity - b.quantity;
        }).slice(0, 6);

        if (!critical.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 24px;">No products found in catalog.</td></tr>`;
            return;
        }

        tbody.innerHTML = critical.map(p => {
            let statusPill = `<span class="pill pill-success">Good Stock</span>`;
            if (p.is_out_of_stock) {
                statusPill = `<span class="pill pill-danger">Out of Stock (0 Left)</span>`;
            } else if (p.is_low_stock) {
                statusPill = `<span class="pill pill-warning">Low (${p.quantity}/${p.reorder_threshold})</span>`;
            }

            const forecast = p.days_until_stockout !== null 
                ? `~${p.days_until_stockout} days left` 
                : 'Steady';

            return `
                <tr>
                    <td>
                        <div style="font-weight: 700; font-size: 0.92rem; color: var(--text-main);">${p.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace;">SKU: ${p.sku} ${p.barcode ? '· ' + p.barcode : ''}</div>
                    </td>
                    <td><span class="pill pill-info">${p.category_name}</span></td>
                    <td>
                        <strong style="font-size: 1rem; color: ${p.is_out_of_stock ? 'var(--alert-danger)' : 'var(--text-main)'};">${p.quantity}</strong>
                        <span style="font-size: 0.75rem; color: var(--text-muted);">${p.unit}</span>
                    </td>
                    <td><strong>${this.state.shop.currency} ${p.sale_price.toFixed(2)}</strong></td>
                    <td>
                        ${statusPill}
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 3px;">${forecast}</div>
                    </td>
                    <td style="text-align: right;">
                        <button class="btn btn-secondary btn-sm" onclick="App.openAdjustModal('${p.id}')">
                            Stock Update
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    filterTransactions(type) {
        this.state.txFilter = type;
        document.querySelectorAll('[data-tx-filter]').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tx-filter') === type);
        });
        this.renderTransactions();
    },

    renderTransactions() {
        const tbody = document.getElementById('dashboard-transactions-body');
        if (!tbody) return;

        let list = this.state.recent_transactions;
        if (this.state.txFilter !== 'all') {
            list = list.filter(t => t.raw_type === this.state.txFilter);
        }

        if (!list.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 24px;">No transactions recorded.</td></tr>`;
            return;
        }

        tbody.innerHTML = list.map(t => {
            const isOut = t.quantity < 0;
            return `
                <tr>
                    <td><strong style="color: var(--text-main);">${t.product_name}</strong></td>
                    <td><span class="pill ${isOut ? 'pill-danger' : 'pill-success'}">${t.transaction_type}</span></td>
                    <td style="font-weight: 800; font-family: monospace; color: ${isOut ? 'var(--alert-danger)' : 'var(--accent-orange)'};">
                        ${isOut ? '' : '+'}${t.quantity}
                    </td>
                    <td style="color: var(--text-muted); font-size: 0.82rem;">${t.note || '—'}</td>
                    <td style="text-align: right; color: var(--text-dim); font-size: 0.8rem;">${t.created_at}</td>
                </tr>
            `;
        }).join('');
    },

    /* ==========================================================================
       Inventory Catalog Studio (CRUD, Filtering, Sorting, Export)
       ========================================================================== */
    populateSelectDropdowns() {
        const catSelect = document.getElementById('category-filter-select');
        const modalCat = document.getElementById('modal-product-category');
        const modalSup = document.getElementById('modal-product-supplier');
        const poSup = document.getElementById('po-supplier-select');

        if (catSelect) {
            catSelect.innerHTML = `<option value="">All Categories (${this.state.categories.length})</option>` +
                this.state.categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
        }
        if (modalCat) {
            modalCat.innerHTML = `<option value="">Select Category</option>` +
                this.state.categories.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
        }
        if (modalSup) {
            modalSup.innerHTML = `<option value="">Select Supplier</option>` +
                this.state.suppliers.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        }
        if (poSup) {
            poSup.innerHTML = `<option value="">Choose Supplier</option>` +
                this.state.suppliers.map(s => `<option value="${s.id}">${s.name} (Lead time: ${s.lead_time_days}d)</option>`).join('');
        }
    },

    applyFilters() {
        const catVal = document.getElementById('category-filter-select')?.value || '';
        const statusVal = document.getElementById('status-filter-select')?.value || 'all';
        const q = this.state.searchQuery.toLowerCase().trim();

        let filtered = this.state.products.filter(p => {
            const matchQuery = !q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || p.barcode.includes(q);
            const matchCat = !catVal || p.category_id === catVal;
            let matchStatus = true;
            if (statusVal === 'healthy') matchStatus = !p.is_low_stock && !p.is_out_of_stock;
            if (statusVal === 'low') matchStatus = p.is_low_stock;
            if (statusVal === 'out') matchStatus = p.is_out_of_stock;
            return matchQuery && matchCat && matchStatus;
        });

        // Apply sorting
        filtered.sort((a, b) => {
            let valA = a[this.state.sortField];
            let valB = b[this.state.sortField];
            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();
            if (valA < valB) return this.state.sortAsc ? -1 : 1;
            if (valA > valB) return this.state.sortAsc ? 1 : -1;
            return 0;
        });

        this.renderCatalogTable(filtered);
    },

    sortProducts(field) {
        if (this.state.sortField === field) {
            this.state.sortAsc = !this.state.sortAsc;
        } else {
            this.state.sortField = field;
            this.state.sortAsc = true;
        }
        this.applyFilters();
    },

    clearSearch() {
        const inp = document.getElementById('product-search-input');
        if (inp) {
            inp.value = '';
            this.state.searchQuery = '';
            document.getElementById('clear-search-btn').style.display = 'none';
            this.applyFilters();
        }
    },

    renderCatalogTable(products) {
        const tbody = document.getElementById('inventory-table-body');
        const countPill = document.getElementById('inventory-count-pill');
        const emptyContainer = document.getElementById('empty-shop-container');
        const tableCard = document.getElementById('catalog-table-card');

        if (countPill) countPill.textContent = `${products.length} products`;

        // If entire shop catalog has 0 products -> Show Empty Shop Card
        if (this.state.products.length === 0) {
            if (emptyContainer) emptyContainer.style.display = 'block';
            if (tableCard) tableCard.style.display = 'none';
            return;
        } else {
            if (emptyContainer) emptyContainer.style.display = 'none';
            if (tableCard) tableCard.style.display = 'block';
        }

        if (!tbody) return;

        if (!products.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 36px;">No products match current filters.</td></tr>`;
            return;
        }

        tbody.innerHTML = products.map(p => {
            let statusPill = `<span class="pill pill-success">Good Stock</span>`;
            if (p.is_out_of_stock) {
                statusPill = `<span class="pill pill-danger">Out of Stock</span>`;
            } else if (p.is_low_stock) {
                statusPill = `<span class="pill pill-warning">Low (${p.quantity}/${p.reorder_threshold})</span>`;
            }

            const forecast = p.days_until_stockout !== null 
                ? `~${p.days_until_stockout} days left` 
                : 'Steady';

            return `
                <tr>
                    <td>
                        <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-main);">${p.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace;">SKU: ${p.sku} ${p.barcode ? '· Barcode: ' + p.barcode : ''}</div>
                    </td>
                    <td><span class="pill pill-info">${p.category_name}</span></td>
                    <td>
                        <strong style="font-size: 1rem; color: ${p.is_out_of_stock ? 'var(--alert-danger)' : 'var(--text-main)'};">${p.quantity}</strong>
                        <span style="font-size: 0.75rem; color: var(--text-muted);">${p.unit}</span>
                    </td>
                    <td><strong>${this.state.shop.currency} ${p.sale_price.toFixed(2)}</strong></td>
                    <td style="color: var(--text-muted);">${this.state.shop.currency} ${p.cost_price.toFixed(2)}</td>
                    <td>
                        ${statusPill}
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 3px;">${forecast}</div>
                    </td>
                    <td style="text-align: right;">
                        <div style="display: inline-flex; gap: 6px;">
                            <button class="btn btn-secondary btn-sm" onclick="App.openAdjustModal('${p.id}')" title="Record stock movement">
                                Update Stock
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="App.openEditProductModal('${p.id}')" title="Edit product details">
                                ✏️
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="App.deleteProduct('${p.id}')" title="Archive product">
                                🗑️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    exportCatalogCSV() {
        if (!this.state.products.length) {
            this.showToast('No products to export', 'error');
            return;
        }
        const headers = ['Name', 'SKU', 'Barcode', 'Category', 'Stock', 'Unit', 'Sale Price', 'Cost Price', 'Reorder Threshold', 'Supplier'];
        const rows = this.state.products.map(p => [
            `"${p.name.replace(/"/g, '""')}"`,
            `"${p.sku}"`,
            `"${p.barcode || ''}"`,
            `"${p.category_name}"`,
            p.quantity,
            `"${p.unit}"`,
            p.sale_price,
            p.cost_price,
            p.reorder_threshold,
            `"${p.supplier_name}"`
        ]);

        const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', `sentrix_inventory_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        this.showToast('Catalog exported to CSV successfully!', 'success');
    },

    /* ==========================================================================
       Sample Data & CSV Import
       ========================================================================== */
    async checkSampleDataStatus() {
        const link = document.getElementById('remove-sample-link');
        if (!link) return;

        try {
            const res = await this.apiFetch('/api/v1/inventory/products/sample-data/');
            if (res.ok) {
                const data = await res.json();
                link.style.display = data.loaded ? 'inline-block' : 'none';
            } else {
                link.style.display = 'none';
            }
        } catch (e) {
            link.style.display = 'none';
        }
    },

    async loadSampleItems() {
        const btn = document.getElementById('btn-show-sample-items');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Adding sample items...';
        }

        try {
            const res = await this.apiFetch('/api/v1/inventory/products/sample-data/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });

            if (res.status === 409) {
                // Already loaded, just refresh
                await this.loadData();
                return;
            }

            if (res.ok) {
                await this.loadData();
                this.showToast(
                    "Done! We've added some sample items so you can see how everything works. You can remove them any time from the button below.",
                    'success'
                );
            } else {
                this.showToast('Something went wrong. Please try again.', 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Show Me Sample Items';
                }
            }
        } catch (e) {
            this.showToast('Something went wrong. Please try again.', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Show Me Sample Items';
            }
        }
    },

    async removeSampleItems() {
        if (!confirm('Are you sure? This will remove all the sample items.')) {
            return;
        }

        try {
            const res = await this.apiFetch('/api/v1/inventory/products/sample-data/', {
                method: 'DELETE',
            });
            if (res.ok) {
                this.showToast('Sample items removed.', 'info');
                await this.loadData();
            } else {
                this.showToast('Something went wrong. Please try again.', 'error');
            }
        } catch (e) {
            this.showToast('Something went wrong. Please try again.', 'error');
        }
    },

    openImportModal() {
        const modal = document.getElementById('import-modal');
        const fileInput = document.getElementById('import-file-input');
        const errBox = document.getElementById('import-error-box');
        const resBox = document.getElementById('import-result-box');
        const submitBtn = document.getElementById('import-submit-btn');

        if (fileInput) fileInput.value = '';
        if (errBox) { errBox.textContent = ''; errBox.style.display = 'none'; }
        if (resBox) { resBox.innerHTML = ''; resBox.style.display = 'none'; }
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Upload'; }

        if (modal) modal.classList.add('active');
    },

    closeImportModal() {
        const modal = document.getElementById('import-modal');
        if (modal) modal.classList.remove('active');
    },

    async submitProductImport() {
        const fileInput = document.getElementById('import-file-input');
        const errBox = document.getElementById('import-error-box');
        const resBox = document.getElementById('import-result-box');
        const submitBtn = document.getElementById('import-submit-btn');

        if (errBox) { errBox.textContent = ''; errBox.style.display = 'none'; }
        if (resBox) { resBox.innerHTML = ''; resBox.style.display = 'none'; }

        const file = fileInput?.files?.[0];
        if (!file) {
            if (errBox) {
                errBox.textContent = 'Please choose a CSV file first.';
                errBox.style.display = 'flex';
            }
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding your products...';

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await this.apiFetch('/api/v1/inventory/products/import/', {
                method: 'POST',
                body: formData,
            });

            const data = await res.json().catch(() => null);

            if (res.status === 400 && data && data.detail) {
                if (errBox) {
                    errBox.textContent = data.detail;
                    errBox.style.display = 'flex';
                }
                submitBtn.disabled = false;
                submitBtn.textContent = 'Upload';
                return;
            }

            if (res.ok && data) {
                const created = data.created || 0;
                const problems = data.problems || [];

                if (problems.length === 0) {
                    this.showToast(`Added ${created} products. All done!`, 'success');
                    this.closeImportModal();
                    await this.loadData();
                } else {
                    let problemListHtml = problems.map(p => `
                        <li style="margin-bottom: 4px; color: var(--alert-danger);">
                            Row ${p.row} (${p.name || 'Unnamed'}): ${p.reason}
                        </li>
                    `).join('');

                    if (resBox) {
                        resBox.style.display = 'block';
                        resBox.innerHTML = `
                            <div class="auth-alert auth-alert-info" style="margin-bottom: 10px;">
                                Added ${created} product${created === 1 ? '' : 's'}. ${problems.length} row${problems.length > 1 ? 's' : ''} had a problem and ${problems.length > 1 ? 'were' : 'was'} skipped:
                            </div>
                            <ul style="font-size: 0.82rem; padding-left: 20px; max-height: 140px; overflow-y: auto;">
                                ${problemListHtml}
                            </ul>
                        `;
                    }
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Upload Another File';
                    await this.loadData();
                }
            } else {
                if (errBox) {
                    errBox.textContent = (data && data.detail) ? data.detail : 'Something went wrong. Please try again.';
                    errBox.style.display = 'flex';
                }
                submitBtn.disabled = false;
                submitBtn.textContent = 'Upload';
            }
        } catch (err) {
            console.error('Import error:', err);
            if (errBox) {
                errBox.textContent = "Can't connect right now. Please check your internet and try again.";
                errBox.style.display = 'flex';
            }
            submitBtn.disabled = false;
            submitBtn.textContent = 'Upload';
        }
    },

    /* ==========================================================================
       Product CRUD Modals
       ========================================================================== */
    openAddProductModal() {
        document.getElementById('product-modal-title').textContent = 'Add New Catalog Product';
        document.getElementById('modal-product-id').value = '';
        document.getElementById('product-modal-form').reset();
        document.getElementById('modal-initial-stock-wrap').style.display = 'block';
        document.getElementById('product-modal').classList.add('active');
    },

    openEditProductModal(productId) {
        const prod = this.state.products.find(p => p.id === productId);
        if (!prod) return;

        document.getElementById('product-modal-title').textContent = `Edit Product: ${prod.name}`;
        document.getElementById('modal-product-id').value = prod.id;
        document.getElementById('modal-product-name').value = prod.name;
        document.getElementById('modal-product-sku').value = prod.sku;
        document.getElementById('modal-product-barcode').value = prod.barcode || '';
        document.getElementById('modal-product-category').value = prod.category_id || '';
        document.getElementById('modal-product-supplier').value = prod.supplier_id || '';
        document.getElementById('modal-product-sale-price').value = prod.sale_price;
        document.getElementById('modal-product-cost-price').value = prod.cost_price;
        document.getElementById('modal-product-threshold').value = prod.reorder_threshold;
        document.getElementById('modal-product-reorder-qty').value = prod.reorder_quantity;
        document.getElementById('modal-product-unit').value = prod.unit;
        document.getElementById('modal-product-expiry').value = prod.expiry_date || '';
        document.getElementById('modal-initial-stock-wrap').style.display = 'none';

        document.getElementById('product-modal').classList.add('active');
    },

    closeProductModal() {
        document.getElementById('product-modal').classList.remove('active');
    },

    async handleProductFormSubmit(e) {
        e.preventDefault();
        const id = document.getElementById('modal-product-id').value;
        const payload = {
            id: id || undefined,
            name: document.getElementById('modal-product-name').value.trim(),
            sku: document.getElementById('modal-product-sku').value.trim(),
            barcode: document.getElementById('modal-product-barcode').value.trim() || undefined,
            category_id: document.getElementById('modal-product-category').value || undefined,
            supplier_id: document.getElementById('modal-product-supplier').value || undefined,
            sale_price: parseFloat(document.getElementById('modal-product-sale-price').value),
            cost_price: parseFloat(document.getElementById('modal-product-cost-price').value || 0),
            initial_stock: parseInt(document.getElementById('modal-product-stock').value || 0, 10),
            reorder_threshold: parseInt(document.getElementById('modal-product-threshold').value || 5, 10),
            reorder_quantity: parseInt(document.getElementById('modal-product-reorder-qty').value || 20, 10),
            unit: document.getElementById('modal-product-unit').value.trim() || 'units',
            expiry_date: document.getElementById('modal-product-expiry').value || undefined,
            shop_id: this.state.shop.id,
        };

        try {
            const res = await this.apiFetch('/api/products/manage/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (res.ok) {
                this.showToast(data.message, 'success');
                this.closeProductModal();
                this.loadData();
            } else {
                this.showToast(data.error || 'Failed to save product', 'error');
            }
        } catch (err) {
            this.showToast('Network error saving product', 'error');
        }
    },

    async deleteProduct(productId) {
        const prod = this.state.products.find(p => p.id === productId);
        if (!prod) return;
        if (!confirm(`Are you sure you want to archive "${prod.name}"?`)) return;

        try {
            const res = await this.apiFetch('/api/products/manage/', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: productId }),
            });
            const data = await res.json();
            if (res.ok) {
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Failed to delete product', 'error');
            }
        } catch (err) {
            this.showToast('Network error deleting product', 'error');
        }
    },

    /* ==========================================================================
       Point of Sale (POS) Engine
       ========================================================================== */
    renderPosProducts() {
        const grid = document.getElementById('pos-products-grid');
        const chips = document.getElementById('pos-category-chips');
        if (!grid) return;

        // Render category chips for POS
        if (chips) {
            chips.innerHTML = `<button class="filter-chip ${this.state.posCategoryFilter === '' ? 'active' : ''}" onclick="App.filterPosCategory('')">All</button>` +
                this.state.categories.map(c => `
                    <button class="filter-chip ${this.state.posCategoryFilter === c.id ? 'active' : ''}" onclick="App.filterPosCategory('${c.id}')">
                        ${c.name}
                    </button>
                `).join('');
        }

        const q = (document.getElementById('pos-search-input')?.value || '').toLowerCase().trim();
        const filtered = this.state.products.filter(p => {
            const matchQ = !q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || p.barcode.includes(q);
            const matchCat = !this.state.posCategoryFilter || p.category_id === this.state.posCategoryFilter;
            return matchQ && matchCat;
        });

        if (!filtered.length) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 40px;">No items match query.</div>`;
            return;
        }

        grid.innerHTML = filtered.map(p => {
            const isOutOfStock = p.quantity <= 0;
            return `
                <div class="pos-product-card ${isOutOfStock ? 'out-of-stock' : ''}" onclick="App.addToCart('${p.id}')">
                    <div>
                        <div class="pos-card-name">${p.name}</div>
                        <div class="pos-card-sku">${p.sku}</div>
                    </div>
                    <div class="pos-card-footer">
                        <div class="pos-card-price">${this.state.shop.currency} ${p.sale_price.toFixed(2)}</div>
                        <div class="pos-card-stock" style="color: ${isOutOfStock ? 'var(--accent-rose)' : 'var(--text-dim)'};">
                            ${isOutOfStock ? 'Out of Stock' : p.quantity + ' ' + p.unit}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    filterPosProducts(val) {
        this.renderPosProducts();
    },

    filterPosCategory(catId) {
        this.state.posCategoryFilter = catId;
        this.renderPosProducts();
    },

    addToCart(productId) {
        const prod = this.state.products.find(p => p.id === productId);
        if (!prod) return;

        if (prod.quantity <= 0) {
            this.playSound('error');
            this.showToast(`"${prod.name}" is out of stock!`, 'error');
            return;
        }

        const existing = this.state.cart.find(item => item.product_id === prod.id);
        if (existing) {
            if (existing.quantity >= prod.quantity) {
                this.playSound('error');
                this.showToast(`Cannot add more than available stock (${prod.quantity})`, 'error');
                return;
            }
            existing.quantity += 1;
        } else {
            this.state.cart.push({
                product_id: prod.id,
                name: prod.name,
                price: prod.sale_price,
                quantity: 1,
                maxStock: prod.quantity,
            });
        }

        this.playSound('beep');
        this.renderCart();
    },

    updateCartQty(productId, delta) {
        const item = this.state.cart.find(i => i.product_id === productId);
        if (!item) return;

        item.quantity += delta;
        if (item.quantity > item.maxStock) {
            item.quantity = item.maxStock;
            this.showToast(`Max available stock reached (${item.maxStock})`, 'error');
        }

        if (item.quantity <= 0) {
            this.state.cart = this.state.cart.filter(i => i.product_id !== productId);
        }

        this.renderCart();
    },

    clearCart() {
        this.state.cart = [];
        this.renderCart();
    },

    renderCart() {
        const container = document.getElementById('pos-cart-items-list');
        const countLabel = document.getElementById('pos-cart-items-count');
        if (!container) return;

        const totalItems = this.state.cart.reduce((acc, i) => acc + i.quantity, 0);
        if (countLabel) countLabel.textContent = `${totalItems} items in cart`;

        if (!this.state.cart.length) {
            container.innerHTML = `
                <div class="empty-cart-state">
                    <div style="font-size: 2.5rem; margin-bottom: 8px;">🛒</div>
                    <p>Cart is empty</p>
                    <span style="font-size: 0.75rem; color: var(--text-dim);">Click items on the left to add to sale</span>
                </div>
            `;
            this.calculateCartTotal();
            return;
        }

        container.innerHTML = this.state.cart.map(item => `
            <div class="pos-cart-item">
                <div class="pos-cart-item-info">
                    <div class="pos-cart-item-title">${item.name}</div>
                    <div class="pos-cart-item-price">${this.state.shop.currency} ${item.price.toFixed(2)} &times; ${item.quantity} = ${this.state.shop.currency} ${(item.price * item.quantity).toFixed(2)}</div>
                </div>
                <div class="pos-qty-stepper">
                    <button class="stepper-btn" onclick="App.updateCartQty('${item.product_id}', -1)">-</button>
                    <span class="stepper-val">${item.quantity}</span>
                    <button class="stepper-btn" onclick="App.updateCartQty('${item.product_id}', 1)">+</button>
                </div>
            </div>
        `).join('');

        this.calculateCartTotal();
    },

    applyDiscountPreset(val, isPercent = false) {
        const subtotal = this.state.cart.reduce((acc, item) => acc + (item.price * item.quantity), 0);
        let discount = 0;
        if (isPercent) {
            discount = Math.round((subtotal * val) / 100);
        } else {
            discount = Math.min(subtotal, val);
        }
        const discountInput = document.getElementById('pos-discount-input');
        if (discountInput) {
            discountInput.value = discount;
            this.calculateCartTotal();
        }
    },

    calculateCartTotal() {
        const subtotal = this.state.cart.reduce((acc, item) => acc + (item.price * item.quantity), 0);
        const discountInput = document.getElementById('pos-discount-input');
        const discount = parseFloat(discountInput?.value || 0) || 0;
        const total = Math.max(0, subtotal - discount);
        const cur = this.state.shop.currency || 'INR';

        const subtotalEl = document.getElementById('pos-subtotal');
        const totalEl = document.getElementById('pos-total');
        if (subtotalEl) subtotalEl.textContent = `${cur} ${subtotal.toFixed(2)}`;
        if (totalEl) totalEl.textContent = `${cur} ${total.toFixed(2)}`;
    },

    async submitPosCheckout() {
        if (!this.state.cart.length) {
            this.showToast('Cannot checkout an empty cart', 'error');
            return;
        }

        const customer = document.getElementById('pos-customer-input')?.value || 'Counter Sale';
        const payment = document.getElementById('pos-payment-select')?.value || 'Cash';
        const discount = parseFloat(document.getElementById('pos-discount-input')?.value || 0) || 0;

        const payload = {
            shop_id: this.state.shop.id,
            customer_name: customer,
            payment_method: payment,
            discount: discount,
            items: this.state.cart.map(i => ({
                product_id: i.product_id,
                quantity: i.quantity,
            }))
        };

        const btn = document.getElementById('pos-checkout-btn');
        if (btn) btn.textContent = 'Processing Sale...';

        try {
            const res = await this.apiFetch('/api/pos/checkout/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (btn) btn.textContent = '⚡ Complete Sale & Print Receipt';

            if (res.ok) {
                this.playSound('chime');
                this.showToast(data.message, 'success');
                this.renderReceiptModal(data.receipt);
                this.clearCart();
                this.loadData();
            } else {
                this.playSound('error');
                this.showToast(data.error || 'Sale transaction failed', 'error');
            }
        } catch (err) {
            if (btn) btn.textContent = '⚡ Complete Sale & Print Receipt';
            this.playSound('error');
            this.showToast('Network error processing sale', 'error');
        }
    },

    renderReceiptModal(rcp) {
        const area = document.getElementById('receipt-printable-area');
        if (!area || !rcp) return;

        area.innerHTML = `
            <div class="receipt-box">
                <div class="receipt-header">
                    <h3 style="font-size: 1.2rem; font-weight: 800;">${rcp.shop_name}</h3>
                    <p style="font-size: 0.75rem; color: #6b7280;">Receipt: ${rcp.receipt_id}</p>
                    <p style="font-size: 0.72rem; color: #6b7280;">${rcp.timestamp}</p>
                    <p style="font-size: 0.75rem; margin-top: 4px;">Customer: <strong>${rcp.customer_name}</strong> &middot; Pay: ${rcp.payment_method}</p>
                </div>
                <div class="receipt-items">
                    ${rcp.items.map(it => `
                        <div class="receipt-row">
                            <span>${it.name} &times; ${it.quantity}</span>
                            <strong>${rcp.currency} ${it.line_total.toFixed(2)}</strong>
                        </div>
                    `).join('')}
                </div>
                <div class="receipt-divider"></div>
                <div class="receipt-row">
                    <span>Subtotal:</span>
                    <span>${rcp.currency} ${rcp.subtotal.toFixed(2)}</span>
                </div>
                ${rcp.discount > 0 ? `
                    <div class="receipt-row" style="color: #dc2626;">
                        <span>Discount:</span>
                        <span>-${rcp.currency} ${rcp.discount.toFixed(2)}</span>
                    </div>
                ` : ''}
                <div class="receipt-divider"></div>
                <div class="receipt-total">
                    <span>TOTAL PAID:</span>
                    <span>${rcp.currency} ${rcp.total.toFixed(2)}</span>
                </div>
                <div style="text-align: center; font-size: 0.72rem; color: #6b7280; margin-top: 14px;">
                    Thank you for your business! &middot; Concurrency Safe Ledger
                </div>
            </div>
        `;

        const modal = document.getElementById('receipt-modal');
        if (modal) modal.classList.add('active');
    },

    closeReceiptModal() {
        document.getElementById('receipt-modal')?.classList.remove('active');
    },

    /* ==========================================================================
       Procurement & Purchase Orders
       ========================================================================== */
    renderSuppliers() {
        const container = document.getElementById('suppliers-overview-container');
        if (!container) return;

        if (!this.state.suppliers.length) {
            container.innerHTML = `<div style="color: var(--text-dim); padding: 14px;">No active suppliers registered.</div>`;
            return;
        }

        container.innerHTML = this.state.suppliers.map(s => `
            <div class="supplier-card">
                <div>
                    <div class="supplier-card-header">
                        <strong style="font-size: 0.95rem; color: var(--text-main);">${s.name}</strong>
                        <span class="pill pill-info">${s.lead_time_days}d Lead Time</span>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">
                        Contact: ${s.contact_name || 'Supplier Rep'} &middot; Tel: ${s.phone_number || 'N/A'}
                    </div>
                </div>
                <div style="margin-top: 12px; display: flex; justify-content: flex-end;">
                    <button class="btn btn-secondary btn-sm" onclick="App.openCustomPOForSupplier('${s.id}')">
                        + Create Order
                    </button>
                </div>
            </div>
        `).join('');
    },

    renderOrders() {
        const container = document.getElementById('orders-list-container');
        if (!container) return;

        if (!this.state.purchase_orders.length) {
            container.innerHTML = `
                <div class="glass-panel" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    <div style="font-size: 2.5rem; margin-bottom: 8px;">📋</div>
                    <p>No purchase orders yet. Click <strong>Auto-Draft Orders</strong> to draft restock orders.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.state.purchase_orders.map(o => {
            const statusPill = {
                draft: 'pill-warning',
                pending: 'pill-warning',
                ordered: 'pill-info',
                received: 'pill-success',
                cancelled: 'pill-danger',
            }[o.status] || 'pill-info';

            const canApprove = o.status === 'draft' || o.status === 'pending';
            const canReceive = o.status === 'ordered';

            return `
                <div class="glass-panel" style="margin-bottom: 16px;">
                    <div class="panel-header">
                        <div>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <strong style="font-size: 1.05rem; color: var(--text-main);">Order #${o.id.substring(0, 8)}</strong>
                                <span class="pill ${statusPill}">${o.status.toUpperCase()}</span>
                            </div>
                            <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 4px;">
                                Supplier: <strong style="color: var(--text-main);">${o.supplier_name}</strong> &middot; Created on ${o.created_at}
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 14px;">
                            <div style="text-align: right;">
                                <div style="font-size: 0.75rem; color: var(--text-dim);">Total Amount</div>
                                <div style="font-weight: 800; font-size: 1.15rem; color: var(--accent-orange); font-family: monospace;">
                                    ${this.state.shop.currency} ${o.total_cost.toLocaleString()}
                                </div>
                            </div>
                            ${canApprove ? `<button class="btn btn-primary btn-sm" onclick="App.approveOrder('${o.id}')">Approve & Order</button>` : ''}
                            ${canReceive ? `<button class="btn btn-secondary btn-sm" onclick="App.receiveOrder('${o.id}')">📥 Receive Items</button>` : ''}
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Item Name</th>
                                    <th>Quantity</th>
                                    <th>Unit Cost</th>
                                    <th style="text-align: right;">Line Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${o.items.map(it => `
                                    <tr>
                                        <td><strong>${it.product_name}</strong></td>
                                        <td>${it.quantity}</td>
                                        <td>${this.state.shop.currency} ${it.unit_cost.toFixed(2)}</td>
                                        <td style="font-weight: 700; text-align: right; color: var(--text-main);">${this.state.shop.currency} ${it.line_total.toFixed(2)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }).join('');
    },

    async approveOrder(orderId) {
        try {
            const res = await this.apiFetch(`/api/orders/${orderId}/approve/`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                this.playSound('beep');
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Approval failed', 'error');
            }
        } catch (err) {
            this.showToast('Network error approving order', 'error');
        }
    },

    async receiveOrder(orderId) {
        try {
            const res = await this.apiFetch(`/api/orders/${orderId}/receive/`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                this.playSound('chime');
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Receiving failed', 'error');
            }
        } catch (err) {
            this.showToast('Network error receiving order', 'error');
        }
    },

    async autoDraftOrders() {
        try {
            const res = await this.apiFetch('/api/orders/auto-draft/', { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                this.playSound('chime');
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Auto-draft failed', 'error');
            }
        } catch (err) {
            this.showToast('Network error auto-drafting POs', 'error');
        }
    },

    /* Custom Purchase Order Creation */
    openCustomPOModal() {
        const wrap = document.getElementById('po-line-items-wrap');
        if (wrap) wrap.innerHTML = '';
        this.addPOLineItemRow();
        document.getElementById('custom-po-modal').classList.add('active');
    },

    openCustomPOForSupplier(supplierId) {
        this.openCustomPOModal();
        const sel = document.getElementById('po-supplier-select');
        if (sel) sel.value = supplierId;
    },

    closeCustomPOModal() {
        document.getElementById('custom-po-modal').classList.remove('active');
    },

    addPOLineItemRow() {
        const wrap = document.getElementById('po-line-items-wrap');
        if (!wrap) return;

        const optionsHtml = this.state.products.map(p => `
            <option value="${p.id}" data-cost="${p.cost_price}">${p.name} (Current: ${p.quantity} ${p.unit})</option>
        `).join('');

        const row = document.createElement('div');
        row.className = 'form-grid-3';
        row.style.marginBottom = '10px';
        row.innerHTML = `
            <div class="form-group" style="margin-bottom:0;">
                <select class="form-control po-item-prod" onchange="App.handlePOItemProductChange(this)">
                    <option value="">Select Item</option>
                    ${optionsHtml}
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0;">
                <input type="number" class="form-control po-item-qty" placeholder="Quantity" min="1" value="20" oninput="App.calculatePOTotal()">
            </div>
            <div class="form-group" style="margin-bottom:0; display: flex; gap: 6px;">
                <input type="number" class="form-control po-item-cost" placeholder="Unit Cost" step="0.01" min="0" oninput="App.calculatePOTotal()">
                <button type="button" class="btn btn-secondary btn-sm" onclick="this.parentElement.parentElement.remove(); App.calculatePOTotal();">&times;</button>
            </div>
        `;
        wrap.appendChild(row);
    },

    handlePOItemProductChange(selectEl) {
        const selectedOpt = selectEl.options[selectEl.selectedIndex];
        const cost = selectedOpt.getAttribute('data-cost') || 0;
        const row = selectEl.closest('.form-grid-3');
        const costInput = row.querySelector('.po-item-cost');
        if (costInput && cost) costInput.value = parseFloat(cost).toFixed(2);
        this.calculatePOTotal();
    },

    calculatePOTotal() {
        let total = 0;
        document.querySelectorAll('#po-line-items-wrap .form-grid-3').forEach(row => {
            const qty = parseFloat(row.querySelector('.po-item-qty')?.value || 0) || 0;
            const cost = parseFloat(row.querySelector('.po-item-cost')?.value || 0) || 0;
            total += (qty * cost);
        });
        const totalEl = document.getElementById('po-estimated-total');
        if (totalEl) totalEl.textContent = `${this.state.shop.currency || 'INR'} ${total.toFixed(2)}`;
    },

    async handleCustomPOSubmit(e) {
        e.preventDefault();
        const supplierId = document.getElementById('po-supplier-select').value;
        const notes = document.getElementById('po-notes-input').value;

        const items = [];
        document.querySelectorAll('#po-line-items-wrap .form-grid-3').forEach(row => {
            const prodId = row.querySelector('.po-item-prod')?.value;
            const qty = parseInt(row.querySelector('.po-item-qty')?.value || 0, 10);
            const cost = parseFloat(row.querySelector('.po-item-cost')?.value || 0);
            if (prodId && qty > 0) {
                items.push({ product_id: prodId, quantity: qty, unit_cost: cost });
            }
        });

        if (!items.length) {
            this.showToast('Please add at least one product item', 'error');
            return;
        }

        try {
            const res = await this.apiFetch('/api/orders/create-custom/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    shop_id: this.state.shop.id,
                    supplier_id: supplierId,
                    notes: notes,
                    items: items,
                })
            });
            const data = await res.json();
            if (res.ok) {
                this.playSound('beep');
                this.showToast(data.message, 'success');
                this.closeCustomPOModal();
                this.loadData();
            } else {
                this.showToast(data.error || 'Failed to create PO', 'error');
            }
        } catch (err) {
            this.showToast('Network error creating PO', 'error');
        }
    },

    /* ==========================================================================
       Safety Alerts
       ========================================================================== */
    renderAlerts() {
        const container = document.getElementById('alerts-list-container');
        if (!container) return;

        if (!this.state.alerts.length) {
            container.innerHTML = `
                <div class="glass-panel" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    <div style="font-size: 2.5rem; margin-bottom: 8px;">🛡️</div>
                    <p>All clear! Zero active alerts or low stock items.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.state.alerts.map(a => {
            const isAck = a.status === 'acknowledged';
            const typeIcon = a.alert_type === 'out_of_stock' ? '🛑' : a.alert_type === 'low_stock' ? '⚠️' : '⏳';
            const pillClass = a.alert_type === 'out_of_stock' ? 'pill-danger' : 'pill-warning';

            return `
                <div class="glass-panel" style="padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; border-left: 4px solid ${a.alert_type === 'out_of_stock' ? 'var(--alert-danger)' : 'var(--accent-orange)'};">
                    <div style="display: flex; align-items: center; gap: 14px;">
                        <span style="font-size: 1.6rem;">${typeIcon}</span>
                        <div>
                            <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-main);">${a.message}</div>
                            <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">
                                ${a.created_at} &middot; Status: <span class="pill ${pillClass}">${a.status}</span>
                            </div>
                        </div>
                    </div>
                    ${!isAck ? `
                        <button class="btn btn-secondary btn-sm" onclick="App.acknowledgeAlert('${a.id}')">
                            ✓ Mark Read
                        </button>
                    ` : '<span style="color: var(--text-muted); font-size: 0.85rem; font-weight: 700;">✓ Read</span>'}
                </div>
            `;
        }).join('');
    },

    async acknowledgeAlert(alertId) {
        try {
            const res = await this.apiFetch(`/api/alerts/${alertId}/acknowledge/`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                this.playSound('beep');
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Acknowledgment failed', 'error');
            }
        } catch (err) {
            this.showToast('Network error acknowledging alert', 'error');
        }
    },

    async acknowledgeAllAlerts() {
        try {
            const res = await this.apiFetch('/api/alerts/acknowledge-all/', { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                this.playSound('beep');
                this.showToast(data.message, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || 'Acknowledging alerts failed', 'error');
            }
        } catch (err) {
            this.showToast('Network error acknowledging alerts', 'error');
        }
    },

    /* ==========================================================================
       Barcode Scanner Simulator
       ========================================================================== */
    openBarcodeModal() {
        const modal = document.getElementById('barcode-modal');
        if (modal) {
            modal.classList.add('active');
            document.getElementById('barcode-input').value = '';
            document.getElementById('barcode-result-card').style.display = 'none';
        }
    },

    closeBarcodeModal() {
        document.getElementById('barcode-modal')?.classList.remove('active');
    },

    pasteSampleBarcode(code) {
        const inp = document.getElementById('barcode-input');
        if (inp) {
            inp.value = code;
            this.handleBarcodeSearch();
        }
    },

    async handleBarcodeSearch() {
        const code = document.getElementById('barcode-input').value.trim();
        if (!code) return;

        try {
            const res = await this.apiFetch('/api/inventory/barcode/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, shop_id: this.state.shop.id }),
            });
            const data = await res.json();
            const card = document.getElementById('barcode-result-card');

            if (res.ok && data.found) {
                this.playSound('beep');
                const p = data.product;
                card.style.display = 'block';
                card.innerHTML = `
                    <div style="background: var(--bg-subtle); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h4 style="font-size: 1.05rem; font-weight: 700; color: var(--text-main);">${p.name}</h4>
                            <p style="color: var(--text-muted); font-size: 0.8rem;">SKU: ${p.sku} &middot; Category: ${p.category_name}</p>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.25rem; font-weight: 800; color: var(--text-main);">${p.quantity} in stock</div>
                            <div style="font-size: 0.95rem; color: var(--accent-orange); font-weight: 700;">${this.state.shop.currency} ${p.sale_price.toFixed(2)}</div>
                        </div>
                    </div>
                    <div style="margin-top: 12px; display: flex; gap: 8px;">
                        <button class="btn btn-secondary btn-sm" onclick="App.closeBarcodeModal(); App.openAdjustModal('${p.id}');">
                            Stock Update
                        </button>
                        <button class="btn btn-primary btn-sm" onclick="App.addToCart('${p.id}'); App.closeBarcodeModal(); App.switchTab('pos');">
                            💳 Add to Bill
                        </button>
                    </div>
                `;
            } else {
                this.playSound('error');
                card.style.display = 'block';
                card.innerHTML = `
                    <div style="background: var(--alert-danger-bg); padding: 12px; border-radius: var(--radius-md); border: 1px solid var(--alert-danger-border); color: var(--alert-danger); font-size: 0.85rem; font-weight: 600;">
                        ${data.message || 'No product found with this barcode.'}
                    </div>
                `;
            }
        } catch (err) {
            this.showToast('Error looking up barcode', 'error');
        }
    },

    /* ==========================================================================
       Quick Stock Adjustment Modal
       ========================================================================== */
    openQuickAdjustModal() {
        if (this.state.products.length > 0) {
            this.openAdjustModal(this.state.products[0].id);
        } else {
            this.showToast('No products available to adjust', 'error');
        }
    },

    openAdjustModal(productId) {
        const product = this.state.products.find(p => p.id === productId);
        if (!product) return;

        this.state.selectedAdjustProduct = product;
        document.getElementById('adjust-product-title').textContent = product.name;
        document.getElementById('adjust-current-stock').textContent = `${product.quantity} ${product.unit}`;
        document.getElementById('adjust-qty-input').value = '1';
        document.getElementById('adjust-note-input').value = '';
        this.selectAdjustType('sale_out');

        const modal = document.getElementById('adjust-stock-modal');
        if (modal) modal.classList.add('active');
    },

    closeAdjustModal() {
        document.getElementById('adjust-stock-modal')?.classList.remove('active');
    },

    selectAdjustType(type) {
        this.state.selectedAdjustType = type;
        document.querySelectorAll('#adjust-pills .pill-option').forEach(el => {
            el.classList.toggle('selected', el.getAttribute('data-type') === type);
        });
    },

    async submitStockAdjustment() {
        const prod = this.state.selectedAdjustProduct;
        const type = this.state.selectedAdjustType || 'sale_out';
        const qty = parseInt(document.getElementById('adjust-qty-input').value, 10);
        const note = document.getElementById('adjust-note-input').value.trim() || 'Recorded via UI';

        if (!prod || isNaN(qty) || qty <= 0) {
            this.showToast('Please enter a valid quantity.', 'error');
            return;
        }

        try {
            const res = await this.apiFetch('/api/inventory/adjust/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    product_id: prod.id,
                    transaction_type: type,
                    quantity: qty,
                    note: note,
                    shop_id: this.state.shop.id,
                })
            });
            const data = await res.json();
            if (res.ok) {
                this.playSound('beep');
                this.showToast(data.message || 'Stock updated successfully!', 'success');
                this.closeAdjustModal();
                this.loadData();
            } else {
                this.playSound('error');
                this.showToast(data.error || 'Failed to update stock', 'error');
            }
        } catch (err) {
            this.showToast('Network error updating stock', 'error');
        }
    },

    /* ==========================================================================
       AI Chatbot Copilot (Claude Tool Execution Loop)
       ========================================================================== */
    async handleChatSubmit() {
        const input = document.getElementById('chat-fullscreen-input');
        const text = input.value.trim();
        if (!text) return;

        input.value = '';
        this.appendChatBubble('user', text);

        const typing = document.getElementById('chat-fullscreen-typing');
        if (typing) typing.style.display = 'flex';

        try {
            const res = await this.apiFetch('/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: this.state.chatSessionId,
                    shop_id: this.state.shop.id,
                })
            });
            const data = await res.json();
            if (typing) typing.style.display = 'none';

            if (res.ok && data.reply) {
                this.playSound('beep');
                this.state.chatSessionId = data.session_id;
                this.appendChatBubble('assistant', data.reply);
                // Background refresh catalog in case tool changed stock or drafted PO
                this.loadData(true);
            } else {
                this.appendChatBubble('assistant', `⚠️ ${data.error || 'Error processing request.'}`);
            }
        } catch (err) {
            if (typing) typing.style.display = 'none';
            this.appendChatBubble('assistant', '⚠️ Network error communicating with Sentrix assistant.');
        }
    },

    sendQuickChip(text) {
        const input = document.getElementById('chat-fullscreen-input');
        if (input) {
            input.value = text;
            this.handleChatSubmit();
        }
    },

    clearChat() {
        const stream = document.getElementById('chat-fullscreen-stream');
        if (stream) {
            this.state.chatSessionId = null;
            stream.innerHTML = `
                <div class="chat-row assistant">
                    <div class="chat-avatar bot-av">🤖</div>
                    <div class="chat-bubble-body">Conversation cleared. How can I assist you with your store inventory?</div>
                </div>
                <div class="chat-row assistant" id="chat-fullscreen-typing" style="display: none;">
                    <div class="chat-avatar bot-av">🤖</div>
                    <div class="chat-bubble-body typing-indicator">
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                        <span style="font-size: 0.75rem; color: var(--text-dim); margin-left: 8px;">Sentrix AI is querying real-time store database...</span>
                    </div>
                </div>
            `;
            this.showToast('Chat history cleared', 'info');
        }
    },

    appendChatBubble(role, text) {
        const stream = document.getElementById('chat-fullscreen-stream');
        const typing = document.getElementById('chat-fullscreen-typing');
        if (!stream) return;

        const row = document.createElement('div');
        row.className = `chat-row ${role}`;

        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code style="background: rgba(0,0,0,0.4); padding: 1px 4px; border-radius: 4px; font-family: monospace;">$1</code>')
            .replace(/\n/g, '<br>');

        row.innerHTML = `
            <div class="chat-avatar ${role === 'user' ? 'user-av' : 'bot-av'}">
                ${role === 'user' ? '👤' : '🤖'}
            </div>
            <div class="chat-bubble-body">${formatted}</div>
        `;

        stream.insertBefore(row, typing);
        stream.scrollTop = stream.scrollHeight;
    },

    /* ==========================================================================
       Global Command Palette (Ctrl+K)
       ========================================================================== */
    openCommandPalette() {
        const modal = document.getElementById('cmd-palette-modal');
        const input = document.getElementById('cmd-palette-input');
        if (modal && input) {
            modal.classList.add('active');
            input.value = '';
            input.focus();
            this.renderCommandPaletteResults('');
        }
    },

    closeCommandPalette() {
        document.getElementById('cmd-palette-modal')?.classList.remove('active');
    },

    renderCommandPaletteResults(query) {
        const resultsContainer = document.getElementById('cmd-palette-results');
        if (!resultsContainer) return;

        const q = (query || '').toLowerCase().trim();

        // 1. Navigation actions
        const navActions = [
            { icon: '📊', title: 'Go to Shop Overview', sub: 'View daily sales, total stock value, and low items', action: () => this.switchTab('dashboard') },
            { icon: '📦', title: 'Open Products & Stock', sub: 'Search items, update quantities, and edit prices', action: () => this.switchTab('inventory') },
            { icon: '💳', title: 'Open Billing Counter', sub: 'Fast counter sales & printed bill (F9)', action: () => this.switchTab('pos') },
            { icon: '📋', title: 'Open Supplier Orders', sub: 'View orders and restock incoming items', action: () => this.switchTab('orders') },
            { icon: '🔔', title: 'View Stock Alerts', sub: 'Check low stock and out of stock items', action: () => this.switchTab('alerts') },
            { icon: '🤖', title: 'Ask Shop AI Assistant', sub: 'Ask stock questions or record sales in plain words', action: () => this.switchTab('chat') },
            { icon: '➕', title: 'Add New Product', sub: 'Add a new item to your shop catalog', action: () => this.openAddProductModal() },
            { icon: '⚡', title: 'Order All Low Stock Items', sub: 'Auto-draft restock orders for low items', action: () => this.autoDraftOrders() },
            { icon: '📷', title: 'Open Barcode Scanner', sub: 'Look up products by scanning or typing code', action: () => this.openBarcodeModal() },
        ].filter(a => !q || a.title.toLowerCase().includes(q) || a.sub.toLowerCase().includes(q));

        // 2. Matching catalog products
        const matchingProducts = this.state.products.filter(p => {
            if (!q) return false;
            return p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || (p.barcode && p.barcode.includes(q));
        }).slice(0, 6);

        let html = '';

        if (matchingProducts.length > 0) {
            html += `<div class="cmd-section-label">Matching Products (${matchingProducts.length})</div>`;
            matchingProducts.forEach((p, index) => {
                html += `
                    <div class="cmd-item" data-cmd-type="product" data-product-id="${p.id}" onclick="App.handleCmdProductClick('${p.id}')">
                        <div class="cmd-item-left">
                            <span class="cmd-item-icon">📦</span>
                            <div>
                                <div class="cmd-item-title">${p.name}</div>
                                <div class="cmd-item-sub">SKU: ${p.sku} &middot; In stock: ${p.quantity} ${p.unit} &middot; ${this.state.shop.currency} ${p.sale_price.toFixed(2)}</div>
                            </div>
                        </div>
                        <div>
                            <span class="pill pill-info" style="font-size: 0.75rem;">Update Stock ↵</span>
                        </div>
                    </div>
                `;
            });
        }

        if (navActions.length > 0) {
            html += `<div class="cmd-section-label">Quick Commands & Navigation</div>`;
            navActions.forEach((a, index) => {
                const selectedClass = (!matchingProducts.length && index === 0) ? 'selected' : '';
                html += `
                    <div class="cmd-item ${selectedClass}" data-cmd-idx="${index}" onclick="App.executeCmdAction(${index})">
                        <div class="cmd-item-left">
                            <span class="cmd-item-icon">${a.icon}</span>
                            <div>
                                <div class="cmd-item-title">${a.title}</div>
                                <div class="cmd-item-sub">${a.sub}</div>
                            </div>
                        </div>
                        <span style="font-size: 0.72rem; color: var(--text-dim);">Jump ↵</span>
                    </div>
                `;
            });
        }

        if (!matchingProducts.length && !navActions.length) {
            html = `<div style="text-align: center; color: var(--text-dim); padding: 32px 16px;">No commands or products matching "${query}".</div>`;
        }

        this._currentNavActions = navActions;
        resultsContainer.innerHTML = html;
    },

    executeCmdAction(idx) {
        if (this._currentNavActions && this._currentNavActions[idx]) {
            this.closeCommandPalette();
            this._currentNavActions[idx].action();
        }
    },

    handleCmdProductClick(productId) {
        this.closeCommandPalette();
        this.openAdjustModal(productId);
    },

    handleCommandPaletteKeydown(e) {
        const items = Array.from(document.querySelectorAll('#cmd-palette-results .cmd-item'));
        if (!items.length) return;

        let currentIndex = items.findIndex(el => el.classList.contains('selected'));

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentIndex >= 0) items[currentIndex].classList.remove('selected');
            currentIndex = (currentIndex + 1) % items.length;
            items[currentIndex].classList.add('selected');
            items[currentIndex].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentIndex >= 0) items[currentIndex].classList.remove('selected');
            currentIndex = (currentIndex - 1 + items.length) % items.length;
            items[currentIndex].classList.add('selected');
            items[currentIndex].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const target = items[currentIndex >= 0 ? currentIndex : 0];
            if (target) target.click();
        }
    },

    copyToClipboard(text, label = 'Code') {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                this.showToast(`${label} copied to clipboard!`, 'info');
            });
        }
    },

    /* ==========================================================================
       Utility Helpers
       ========================================================================== */
    closeAllModals() {
        document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.remove('active'));
    },

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        const icons = { success: '✅', error: '❌', info: 'ℹ️' };
        toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(50px)';
            setTimeout(() => toast.remove(), 300);
        }, 3600);
    },

    setSafeText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }
};

// Start application when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
