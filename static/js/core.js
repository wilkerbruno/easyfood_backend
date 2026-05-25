// =============================================================
//  EASYFOOD - API Client + Cart + Utilities (JavaScript)
// =============================================================

const API_BASE = "";  // same origin

// ── HTTP Client ───────────────────────────────────────────────
const http = {
  _sessionToken:  localStorage.getItem("ef_session") || "",
  _employeeToken: localStorage.getItem("ef_employee") || "",

  setSession(token)  { this._sessionToken  = token; localStorage.setItem("ef_session", token); },
  setEmployee(token) { this._employeeToken = token; localStorage.setItem("ef_employee", token); },
  clearSession()     { this._sessionToken  = ""; localStorage.removeItem("ef_session"); },
  clearEmployee()    { this._employeeToken = ""; localStorage.removeItem("ef_employee"); },

  async request(method, path, data = null, useEmployee = false) {
    const headers = { "Content-Type": "application/json" };
    const token = useEmployee ? this._employeeToken : this._sessionToken;
    if (token) {
      if (useEmployee) headers["Authorization"] = `Bearer ${token}`;
      else             headers["X-Session-Token"] = token;
    }
    try {
      const res = await fetch(API_BASE + path, {
        method,
        headers,
        body: data ? JSON.stringify(data) : undefined,
      });
      const body = await res.json();
      return { status: res.status, body };
    } catch (e) {
      return { status: 0, body: { error: e.message } };
    }
  },

  // ── Customer ─────────────────────────────────────────────
  startSession: (qr, table, name) =>
    http.request("POST", "/api/v1/customer/session/start", { qr_code_token: qr, table_number: table, name }),

  getRestaurants: () =>
    http.request("GET", "/api/v1/customer/restaurants"),

  getMenu: (id) =>
    http.request("GET", `/api/v1/customer/restaurants/${id}/menu`),

  createOrder: (restaurantId, items, notes) =>
    http.request("POST", "/api/v1/customer/orders", { restaurant_id: restaurantId, items, notes }),

  getOrders: () =>
    http.request("GET", "/api/v1/customer/orders"),

  getOrder: (id) =>
    http.request("GET", `/api/v1/customer/orders/${id}`),

  payOrder: (id, method) =>
    http.request("POST", `/api/v1/customer/orders/${id}/pay`, { method }),

  reviewOrder: (id, rating, comment) =>
    http.request("POST", `/api/v1/customer/orders/${id}/review`, { rating, comment }),

  // ── Restaurant ───────────────────────────────────────────
  employeeLogin: (email, password) =>
    http.request("POST", "/api/v1/restaurant/auth/login", { email, password }),

  getDashboard: () =>
    http.request("GET", "/api/v1/restaurant/dashboard", null, true),

  getRestaurantOrders: (status = "") =>
    http.request("GET", `/api/v1/restaurant/orders${status ? "?status=" + status : ""}`, null, true),

  updateOrderStatus: (id, status) =>
    http.request("PATCH", `/api/v1/restaurant/orders/${id}/status`, { status }, true),

  getInventory: () =>
    http.request("GET", "/api/v1/restaurant/inventory", null, true),

  createInventoryItem: (data) =>
    http.request("POST", "/api/v1/restaurant/inventory", data, true),

  updateInventoryItem: (id, data) =>
    http.request("PUT", `/api/v1/restaurant/inventory/${id}`, data, true),

  addMovement: (itemId, type, qty, reason) =>
    http.request("POST", `/api/v1/restaurant/inventory/${itemId}/movement`,
      { movement_type: type, quantity: qty, reason }, true),

  getSalesReport: (from, to) =>
    http.request("GET", `/api/v1/restaurant/reports/sales?date_from=${from}&date_to=${to}`, null, true),

  getRestaurantMenu: () =>
    http.request("GET", "/api/v1/restaurant/menu", null, true),

  createMenuItem: (data) =>
    http.request("POST", "/api/v1/restaurant/menu/items", data, true),

  updateMenuItem: (id, data) =>
    http.request("PUT", `/api/v1/restaurant/menu/items/${id}`, data, true),
};

// ── Cart ──────────────────────────────────────────────────────
const cart = {
  items: {},           // id → { item, quantity, notes }
  restaurantId: null,

  setRestaurant(id) {
    if (this.restaurantId !== id) this.clear();
    this.restaurantId = id;
  },

  add(item, qty = 1, notes = "") {
    const id = item.id;
    if (this.items[id]) this.items[id].quantity += qty;
    else this.items[id] = { item, quantity: qty, notes };
    this._notify();
  },

  updateQty(id, delta) {
    if (!this.items[id]) return;
    this.items[id].quantity += delta;
    if (this.items[id].quantity <= 0) delete this.items[id];
    this._notify();
  },

  remove(id) { delete this.items[id]; this._notify(); },

  clear() { this.items = {}; this._notify(); },

  get list()  { return Object.values(this.items); },
  get count() { return this.list.reduce((s, e) => s + e.quantity, 0); },
  get total() { return this.list.reduce((s, e) => s + e.item.price * e.quantity, 0); },
  get empty() { return this.list.length === 0; },

  toPayload() {
    return this.list.map(e => ({
      menu_item_id: e.item.id,
      quantity: e.quantity,
      notes: e.notes,
    }));
  },

  _notify() { document.dispatchEvent(new CustomEvent("cart:updated")); },
};

// ── Utilities ─────────────────────────────────────────────────
const fmt = {
  currency: (v) => `R$ ${Number(v).toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`,
  date:     (s) => s ? new Date(s).toLocaleString("pt-BR", { day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit" }) : "",
  dateOnly: (s) => s ? new Date(s + "T00:00:00").toLocaleDateString("pt-BR") : "",
};

const statusLabel = { pending:"Aguardando", confirmed:"Confirmado", preparing:"Preparando", ready:"Pronto! 🎉", delivered:"Entregue", cancelled:"Cancelado" };
const statusClass = { pending:"badge-pending", confirmed:"badge-confirmed", preparing:"badge-preparing", ready:"badge-ready", delivered:"badge-delivered", cancelled:"badge-cancelled" };

function badge(status) {
  return `<span class="badge ${statusClass[status] || ''}">${statusLabel[status] || status}</span>`;
}

function toast(msg, type = "info") {
  document.querySelectorAll(".toast").forEach(t => t.remove());
  const el = document.createElement("div");
  el.className = "toast";
  el.style.borderLeftColor = type === "error" ? "var(--danger)" : type === "success" ? "var(--success)" : "var(--primary)";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

function spinner() {
  return `<div class="spinner"></div>`;
}

// ── Auth do Cliente ───────────────────────────────────────────
http.register = (name, email, phone, password) =>
  http.request("POST", "/api/v1/auth/register", { name, email, phone, password });

http.loginUser = (email, password) =>
  http.request("POST", "/api/v1/auth/login", { email, password });

http.scanQR = (qr_token, table_number, name) =>
  http.request("POST", "/api/v1/auth/scan", { qr_token, table_number, name },
    !!http._userToken);  // usa token de usuário se tiver

http.getMe = () =>
  http.request("GET", "/api/v1/auth/me", null, false, "user");

// Token do usuário (conta criada)
Object.defineProperty(http, "_userToken", {
  get() { return localStorage.getItem("ef_user") || ""; },
});
http.setUserToken  = (t) => localStorage.setItem("ef_user", t);
http.clearUserToken= ()  => localStorage.removeItem("ef_user");

// Sobrescreve request para suportar token de usuário
const _origRequest = http.request.bind(http);
http.request = async function(method, path, data=null, useEmployee=false, tokenType=null) {
  const headers = { "Content-Type": "application/json" };
  let token = "";
  if (useEmployee)             token = this._employeeToken;
  else if (tokenType==="user") token = this._userToken;
  else                         token = this._sessionToken;

  if (token) {
    if (useEmployee || tokenType==="user") headers["Authorization"] = `Bearer ${token}`;
    else headers["X-Session-Token"] = token;
  }
  try {
    const res  = await fetch(API_BASE + path, { method, headers, body: data ? JSON.stringify(data) : undefined });
    const body = await res.json();
    return { status: res.status, body };
  } catch(e) {
    return { status: 0, body: { error: e.message } };
  }
};

// ── QR Codes (restaurante) ────────────────────────────────────
http.getQRCodes    = ()         => http.request("GET",    "/api/v1/restaurant/qrcodes",     null, true);
http.createQRCodes = (data)     => http.request("POST",   "/api/v1/restaurant/qrcodes",     data, true);
http.deleteQRCode  = (id)       => http.request("DELETE", `/api/v1/restaurant/qrcodes/${id}`, null, true);

// Limpa sessão do cliente
http.clearSession = () => {
  http._sessionToken = "";
  localStorage.removeItem("ef_session");
};
