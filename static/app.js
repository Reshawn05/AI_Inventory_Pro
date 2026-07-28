document.addEventListener("DOMContentLoaded", () => {
    // State
    let currentInventory = [];
    let isLowStockFilterActive = false;

    // DOM Elements - Navigation
    const navTabs = document.querySelectorAll(".nav-tab");
    const tabContents = document.querySelectorAll(".tab-content");

    // Dashboard Elements
    const kpiTotalVal = document.getElementById("kpi-total-val");
    const kpiTotalItems = document.getElementById("kpi-total-items");
    const kpiTotalQty = document.getElementById("kpi-total-qty");
    const kpiLowStock = document.getElementById("kpi-low-stock");
    const kpiCategories = document.getElementById("kpi-categories");
    const dashLowStockBody = document.getElementById("dashboard-low-stock-body");

    // Products Elements
    const searchInput = document.getElementById("products-search-input");
    const clearSearchBtn = document.getElementById("btn-clear-search");
    const categoryFilter = document.getElementById("filter-category");
    const lowStockBtn = document.getElementById("btn-filter-low-stock");
    const refreshBtn = document.getElementById("btn-refresh-inventory");
    const tableBody = document.getElementById("inventory-table-body");

    // Modals
    const addModal = document.getElementById("add-modal");
    const editModal = document.getElementById("edit-modal");
    const btnOpenAddModal = document.getElementById("btn-open-add-modal");
    const dashBtnAddProduct = document.getElementById("dash-btn-add-product");
    const modalCloseBtns = document.querySelectorAll(".modal-close");
    const addProductForm = document.getElementById("add-product-form");
    const editProductForm = document.getElementById("edit-product-form");

    // Reports Elements
    const reportValuation = document.getElementById("report-valuation");
    const reportTotalUnits = document.getElementById("report-total-units");
    const reportSkus = document.getElementById("report-skus");
    const reportWarnings = document.getElementById("report-warnings");
    const categoryDistContainer = document.getElementById("category-distribution-container");
    const btnRefreshReports = document.getElementById("btn-refresh-reports");

    // Warehouse Elements
    const warehouseCardsContainer = document.getElementById("warehouse-cards-container");
    const btnRefreshWarehouse = document.getElementById("btn-refresh-warehouse");
    const dashBtnViewWarehouse = document.getElementById("dash-btn-view-warehouse");

    // AI Assistant Elements
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");
    const chipBtns = document.querySelectorAll(".chip-btn");
    const dashBtnOpenAi = document.getElementById("dash-btn-open-ai");

    // Initialize App
    initApp();

    function initApp() {
        setupNavigation();
        setupModals();
        setupProductsListeners();
        setupAIChat();

        // Initial Data Load
        loadDashboardData();
        loadProductsData();
        loadReportsData();
        loadWarehouseData();
    }

    // ----------------------------------------------------
    // Tab Navigation
    // ----------------------------------------------------
    function setupNavigation() {
        navTabs.forEach(tab => {
            tab.addEventListener("click", () => {
                const targetTabId = tab.getAttribute("data-tab");
                if (!targetTabId) return;

                switchTab(targetTabId);
            });
        });

        // Dashboard quick links
        const btnGotoProducts = document.getElementById("btn-goto-products");
        if (btnGotoProducts) {
            btnGotoProducts.addEventListener("click", () => switchTab("products-tab"));
        }

        if (dashBtnViewWarehouse) {
            dashBtnViewWarehouse.addEventListener("click", () => switchTab("warehouse-tab"));
        }

        if (dashBtnOpenAi) {
            dashBtnOpenAi.addEventListener("click", () => switchTab("assistant-tab"));
        }

        if (dashBtnAddProduct) {
            dashBtnAddProduct.addEventListener("click", () => {
                if (addProductForm) addProductForm.reset();
                if (addModal) addModal.classList.add("active");
            });
        }
    }

    function switchTab(tabId) {
        navTabs.forEach(t => t.classList.remove("active"));
        tabContents.forEach(c => c.classList.remove("active"));

        const activeTab = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
        const targetContent = document.getElementById(tabId);

        if (activeTab) activeTab.classList.add("active");
        if (targetContent) targetContent.classList.add("active");

        if (tabId === "reports-tab") loadReportsData();
        if (tabId === "warehouse-tab") loadWarehouseData();
        if (tabId === "products-tab") loadProductsData();
    }

    // ----------------------------------------------------
    // Dashboard Data & Low Stock Overview
    // ----------------------------------------------------
    async function loadDashboardData() {
        try {
            const res = await fetch("/api/summary");
            if (!res.ok) return;
            const data = await res.json();

            if (kpiTotalVal) kpiTotalVal.textContent = `₹${(data.total_inventory_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
            if (kpiTotalItems) kpiTotalItems.textContent = data.total_items || 0;
            if (kpiTotalQty) kpiTotalQty.textContent = `${(data.total_quantity || 0).toLocaleString('en-IN')} units in stock`;
            if (kpiLowStock) kpiLowStock.textContent = data.low_stock_items_count || 0;
            if (kpiCategories) kpiCategories.textContent = data.categories_count || 0;

            loadDashboardLowStockTable();
        } catch (err) {
            console.error("Error loading dashboard summary:", err);
        }
    }

    async function loadDashboardLowStockTable() {
        if (!dashLowStockBody) return;
        try {
            const res = await fetch("/api/inventory?low_stock_only=true");
            if (!res.ok) return;
            const data = await res.json();
            const items = data.items || [];

            if (items.length === 0) {
                dashLowStockBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #10b981; padding: 25px;"><i class="fa-solid fa-circle-check"></i> Excellent! All products are currently above minimum stock thresholds.</td></tr>`;
                return;
            }

            dashLowStockBody.innerHTML = items.map(item => `
                <tr>
                    <td><span class="sku-tag">${item.sku}</span></td>
                    <td><strong>${escapeHtml(item.name)}</strong></td>
                    <td><span class="badge badge-primary">${escapeHtml(item.category)}</span></td>
                    <td><span class="text-danger" style="color: #ef4444; font-weight: 700;">${item.quantity} units</span></td>
                    <td>${item.min_stock_threshold} units</td>
                    <td><i class="fa-solid fa-location-dot" style="color: var(--text-muted);"></i> ${escapeHtml(item.location)}</td>
                    <td><span class="badge badge-warning"><i class="fa-solid fa-triangle-exclamation"></i> Low Stock</span></td>
                </tr>
            `).join("");
        } catch (err) {
            console.error("Error loading dashboard low stock table:", err);
        }
    }

    // ----------------------------------------------------
    // Products Table & Filtering
    // ----------------------------------------------------
    async function loadProductsData() {
        if (!tableBody) return;

        const query = searchInput ? searchInput.value.trim() : "";
        const category = categoryFilter ? categoryFilter.value : "";
        const lowStock = isLowStockFilterActive;

        const params = new URLSearchParams();
        if (query) params.append("query", query);
        if (category) params.append("category", category);
        if (lowStock) params.append("low_stock_only", "true");

        try {
            const res = await fetch(`/api/inventory?${params.toString()}`);
            if (!res.ok) throw new Error("Failed to load inventory");
            const data = await res.json();
            currentInventory = data.items || [];
            renderProductsTable(currentInventory);
        } catch (err) {
            console.error("Error fetching products:", err);
            tableBody.innerHTML = `<tr><td colspan="9" class="loading-state text-danger" style="text-align: center; color: #ef4444; padding: 30px;">Error loading products catalog</td></tr>`;
        }
    }

    function renderProductsTable(items) {
        if (!items || items.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">No products found matching your current filter criteria.</td></tr>`;
            return;
        }

        tableBody.innerHTML = items.map(item => {
            const isLowStock = item.quantity <= item.min_stock_threshold;
            const stockDisplay = isLowStock 
                ? `<span style="color: #f59e0b; font-weight: 700;"><i class="fa-solid fa-triangle-exclamation"></i> ${item.quantity}</span>`
                : `<strong>${item.quantity}</strong>`;

            return `
                <tr>
                    <td>#${item.id}</td>
                    <td><span class="sku-tag">${item.sku}</span></td>
                    <td><strong>${escapeHtml(item.name)}</strong></td>
                    <td><span class="badge badge-primary">${escapeHtml(item.category)}</span></td>
                    <td>₹${(item.unit_price || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td>${stockDisplay}</td>
                    <td>${item.min_stock_threshold}</td>
                    <td><i class="fa-solid fa-location-dot" style="color: var(--text-muted); margin-right: 4px;"></i> ${escapeHtml(item.location)}</td>
                    <td>
                        <div class="action-btns">
                            <button class="btn-icon-only edit" title="Edit Item" onclick="openEditModal(${item.id})">
                                <i class="fa-solid fa-pen"></i>
                            </button>
                            <button class="btn-icon-only delete" title="Delete Item" onclick="handleDeleteItem(${item.id})">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function setupProductsListeners() {
        let debounceTimer;
        if (searchInput) {
            searchInput.addEventListener("input", () => {
                if (clearSearchBtn) {
                    clearSearchBtn.style.display = searchInput.value.length > 0 ? "block" : "none";
                }
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(loadProductsData, 250);
            });
        }

        if (clearSearchBtn) {
            clearSearchBtn.addEventListener("click", () => {
                if (searchInput) searchInput.value = "";
                clearSearchBtn.style.display = "none";
                loadProductsData();
            });
        }

        if (categoryFilter) {
            categoryFilter.addEventListener("change", loadProductsData);
        }

        if (lowStockBtn) {
            lowStockBtn.addEventListener("click", () => {
                isLowStockFilterActive = !isLowStockFilterActive;
                if (isLowStockFilterActive) {
                    lowStockBtn.classList.remove("btn-outline");
                    lowStockBtn.classList.add("btn-primary");
                } else {
                    lowStockBtn.classList.remove("btn-primary");
                    lowStockBtn.classList.add("btn-outline");
                }
                loadProductsData();
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => {
                loadProductsData();
                loadDashboardData();
                showToast("Inventory products refreshed!", "success");
            });
        }
    }

    // ----------------------------------------------------
    // Modals & Product CRUD Operations
    // ----------------------------------------------------
    function setupModals() {
        if (btnOpenAddModal && addModal && addProductForm) {
            btnOpenAddModal.addEventListener("click", () => {
                addProductForm.reset();
                addModal.classList.add("active");
            });
        }

        modalCloseBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                if (addModal) addModal.classList.remove("active");
                if (editModal) editModal.classList.remove("active");
            });
        });

        if (addProductForm) {
            addProductForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                const payload = {
                    sku: document.getElementById("add-sku").value.trim(),
                    name: document.getElementById("add-name").value.trim(),
                    category: document.getElementById("add-category").value,
                    unit_price: parseFloat(document.getElementById("add-price").value),
                    quantity: parseInt(document.getElementById("add-qty").value, 10),
                    min_stock_threshold: parseInt(document.getElementById("add-threshold").value, 10),
                    location: document.getElementById("add-location").value.trim(),
                    description: document.getElementById("add-desc").value.trim()
                };

                try {
                    const res = await fetch("/api/inventory", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Failed to add product");

                    if (addModal) addModal.classList.remove("active");
                    showToast(`Product '${payload.name}' added successfully!`, "success");
                    loadProductsData();
                    loadDashboardData();
                } catch (err) {
                    showToast(err.message, "danger");
                }
            });
        }

        if (editProductForm) {
            editProductForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                const id = document.getElementById("edit-id").value;
                const payload = {
                    name: document.getElementById("edit-name").value.trim(),
                    category: document.getElementById("edit-category").value,
                    unit_price: parseFloat(document.getElementById("edit-price").value),
                    quantity: parseInt(document.getElementById("edit-qty").value, 10),
                    min_stock_threshold: parseInt(document.getElementById("edit-threshold").value, 10),
                    location: document.getElementById("edit-location").value.trim(),
                    description: document.getElementById("edit-desc").value.trim()
                };

                try {
                    const res = await fetch(`/api/inventory/${id}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Failed to update product");

                    if (editModal) editModal.classList.remove("active");
                    showToast(`Product #${id} updated successfully!`, "success");
                    loadProductsData();
                    loadDashboardData();
                } catch (err) {
                    showToast(err.message, "danger");
                }
            });
        }
    }

    window.openEditModal = function(id) {
        const item = currentInventory.find(i => i.id === id);
        if (!item) return;

        document.getElementById("edit-id").value = item.id;
        document.getElementById("edit-sku").value = item.sku;
        document.getElementById("edit-name").value = item.name;
        document.getElementById("edit-category").value = item.category;
        document.getElementById("edit-price").value = item.unit_price;
        document.getElementById("edit-qty").value = item.quantity;
        document.getElementById("edit-threshold").value = item.min_stock_threshold;
        document.getElementById("edit-location").value = item.location;
        document.getElementById("edit-desc").value = item.description || "";

        if (editModal) editModal.classList.add("active");
    };

    window.handleDeleteItem = async function(id) {
        const item = currentInventory.find(i => i.id === id);
        const name = item ? item.name : `Item #${id}`;
        if (!confirm(`Are you sure you want to delete "${name}" (ID #${id})?`)) return;

        try {
            const res = await fetch(`/api/inventory/${id}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Delete failed");
            showToast(`Product "${name}" removed.`, "success");
            loadProductsData();
            loadDashboardData();
        } catch (err) {
            showToast(err.message, "danger");
        }
    };

    // ----------------------------------------------------
    // Reports Tab Logic
    // ----------------------------------------------------
    async function loadReportsData() {
        if (btnRefreshReports) {
            btnRefreshReports.onclick = loadReportsData;
        }

        try {
            const res = await fetch("/api/summary");
            if (!res.ok) return;
            const data = await res.json();
            const report = data.clean_report || {};

            if (reportValuation) reportValuation.textContent = report.total_inventory_valuation || `₹${(data.total_inventory_value || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            if (reportTotalUnits) reportTotalUnits.textContent = `${(data.total_quantity || 0).toLocaleString('en-IN')} Units`;
            if (reportSkus) reportSkus.textContent = `${data.total_items || 0} Products`;
            if (reportWarnings) reportWarnings.textContent = `${data.low_stock_items_count || 0} Alerts`;

            // Category breakdown
            const invRes = await fetch("/api/inventory");
            const invData = await invRes.json();
            const items = invData.items || [];

            const catMap = {};
            items.forEach(i => {
                if (!catMap[i.category]) catMap[i.category] = { count: 0, units: 0, val: 0 };
                catMap[i.category].count += 1;
                catMap[i.category].units += i.quantity;
                catMap[i.category].val += (i.quantity * i.unit_price);
            });

            if (categoryDistContainer) {
                categoryDistContainer.innerHTML = Object.keys(catMap).map(cat => {
                    const info = catMap[cat];
                    return `
                        <div class="category-card">
                            <div class="cat-header">
                                <span class="cat-name">${escapeHtml(cat)}</span>
                                <span class="badge badge-primary">${info.count} SKUs</span>
                            </div>
                            <h3 class="cat-val">₹${info.val.toLocaleString('en-IN', {minimumFractionDigits: 2})}</h3>
                            <div class="cat-sub">${info.units.toLocaleString('en-IN')} units in stock</div>
                        </div>
                    `;
                }).join("");
            }
        } catch (err) {
            console.error("Error loading reports data:", err);
        }
    }

    // ----------------------------------------------------
    // Warehouse Locations Tab Logic
    // ----------------------------------------------------
    async function loadWarehouseData() {
        if (!warehouseCardsContainer) return;
        if (btnRefreshWarehouse) btnRefreshWarehouse.onclick = loadWarehouseData;

        try {
            const res = await fetch("/api/warehouse");
            if (!res.ok) throw new Error("Failed to load warehouse overview");
            const data = await res.json();
            const locations = data.locations || [];

            if (locations.length === 0) {
                warehouseCardsContainer.innerHTML = `<div class="loading-state" style="grid-column: 1/-1;">No warehouse locations found.</div>`;
                return;
            }

            warehouseCardsContainer.innerHTML = locations.map(loc => {
                const capPct = loc.capacity_pct || 0;
                let statusColor = "var(--primary-color)";
                if (capPct > 80) statusColor = "#ef4444";
                else if (capPct > 60) statusColor = "#f59e0b";

                const itemListHtml = (loc.items || []).map(item => `
                    <div class="wh-item-chip">
                        <span><strong>${escapeHtml(item.name)}</strong> (${item.sub_location || loc.name})</span>
                        <span class="badge badge-secondary">${item.quantity} units</span>
                    </div>
                `).join("");

                return `
                    <div class="card warehouse-card">
                        <div class="wh-card-header">
                            <div>
                                <h3 class="wh-title"><i class="fa-solid fa-warehouse" style="color: var(--primary-color);"></i> ${escapeHtml(loc.name)}</h3>
                                <span class="wh-sub">${loc.products} Products Stored</span>
                            </div>
                            <span class="wh-units-badge">${loc.units.toLocaleString()} Units</span>
                        </div>

                        <div class="gauge-container">
                            <div class="gauge-header">
                                <span>Facility Capacity Utilization</span>
                                <strong>${capPct}%</strong>
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill" style="width: ${capPct}%; background-color: ${statusColor};"></div>
                            </div>
                        </div>

                        <div class="wh-items-section">
                            <h4>Stored Products</h4>
                            <div class="wh-items-list">
                                ${itemListHtml || '<span style="color: var(--text-muted);">No products registered.</span>'}
                            </div>
                        </div>
                    </div>
                `;
            }).join("");
        } catch (err) {
            console.error("Error loading warehouse cards:", err);
            warehouseCardsContainer.innerHTML = `<div class="loading-state text-danger" style="grid-column: 1/-1;">Failed to load warehouse location data.</div>`;
        }
    }

    // ----------------------------------------------------
    // AI Assistant Chat Form
    // ----------------------------------------------------
    function setupAIChat() {
        if (!chatForm || !chatInput || !chatMessages) return;

        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const msg = chatInput.value.trim();
            if (!msg) return;

            sendChatMessage(msg);
            chatInput.value = "";
        });

        chipBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                const prompt = btn.getAttribute("data-prompt");
                if (prompt) {
                    sendChatMessage(prompt);
                }
            });
        });
    }

    async function sendChatMessage(userText) {
        // Append user bubble
        appendChatBubble("user", userText);

        // Typing indicator
        const typingId = "typing-" + Date.now();
        appendTypingIndicator(typingId);

        try {
            const res = await fetch("/api/ai/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: userText })
            });

            removeTypingIndicator(typingId);

            if (!res.ok) throw new Error("Assistant response failed.");
            const data = await res.json();

            appendChatBubble("assistant", data.reply, data.mcp_action);
        } catch (err) {
            removeTypingIndicator(typingId);
            appendChatBubble("assistant", "Sorry, I encountered an error processing your request. Please try again.");
        }
    }

    function formatMarkdown(text) {
        if (!text) return "";

        // Escape HTML first to prevent XSS
        let html = escapeHtml(text);

        // Convert headings ### Title
        html = html.replace(/^### (.*$)/gim, '<h5 class="ai-msg-heading">$1</h5>');
        html = html.replace(/^## (.*$)/gim, '<h4 class="ai-msg-heading">$1</h4>');

        // Convert bold text **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');

        // Highlight Action Needed / Alert tags
        html = html.replace(/(Action Needed:|Action Required:|Reorder Alert:|Warning:)/gi, 
            '<span class="ai-action-badge"><i class="fa-solid fa-triangle-exclamation"></i> $1</span>');

        // Highlight Currency values
        html = html.replace(/(₹[\d,]+(?:\.\d{2})?)/g, '<span class="ai-price-tag">$1</span>');

        // Convert bullet lists (* item, - item, • item)
        const lines = html.split('\n');
        let inList = false;
        let resultLines = [];

        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
                if (!inList) {
                    inList = true;
                    resultLines.push('<ul class="ai-msg-list">');
                }
                const itemText = trimmed.replace(/^[\*\-\•]\s*/, '');
                resultLines.push(`<li>${itemText}</li>`);
            } else {
                if (inList) {
                    inList = false;
                    resultLines.push('</ul>');
                }
                if (trimmed.length > 0) {
                    resultLines.push(`<p class="ai-msg-paragraph">${trimmed}</p>`);
                }
            }
        });

        if (inList) {
            resultLines.push('</ul>');
        }

        return resultLines.join('\n');
    }

    function appendChatBubble(sender, text, mcpAction = null) {
        const bubble = document.createElement("div");
        bubble.className = `chat-message ${sender}`;

        const avatarIcon = sender === "assistant" ? "fa-robot" : "fa-user";
        const formattedContent = sender === "assistant" ? formatMarkdown(text) : `<p class="ai-msg-paragraph">${escapeHtml(text)}</p>`;

        let actionTag = "";
        if (mcpAction) {
            actionTag = `<div class="mcp-action-pill"><i class="fa-solid fa-server"></i> ${escapeHtml(mcpAction)}</div>`;
        }

        bubble.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid ${avatarIcon}"></i></div>
            <div class="msg-content">
                ${actionTag}
                ${formattedContent}
            </div>
        `;

        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendTypingIndicator(id) {
        const bubble = document.createElement("div");
        bubble.className = "chat-message assistant";
        bubble.id = id;
        bubble.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-content">
                <p><i class="fa-solid fa-ellipsis fa-bounce"></i> Assistant is processing your request...</p>
            </div>
        `;
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTypingIndicator(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // Helper functions
    function showToast(msg, type = "success") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `<i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation'}"></i> ${escapeHtml(msg)}`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3500);
    }

    function escapeHtml(str) {
        if (typeof str !== "string") return str;
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
});
