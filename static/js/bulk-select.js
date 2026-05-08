/**
 * bulk-select.js
 * Adds checkbox-based bulk selection + floating delete bar to any table.
 *
 * Usage in template:
 *   <table data-bulk-url="/admin/students/bulk-delete" data-bulk-label="student">
 *     <thead>
 *       <tr>
 *         <th><input type="checkbox" data-bulk-select-all class="bulk-cb"></th>
 *         ...
 *       </tr>
 *     </thead>
 *     <tbody>
 *       {% for s in students %}
 *       <tr>
 *         <td><input type="checkbox" data-bulk-item value="{{ s.id }}"
 *                    data-bulk-name="{{ s.user.name }}" class="bulk-cb"></td>
 *         ...
 *       </tr>
 *     </tbody>
 *   </table>
 */
(function () {
  'use strict';

  /* ── Floating Action Bar ───────────────────────────────────────────── */
  let _bar        = null;
  let _currentUrl = '';
  let _currentIds = [];

  function _getBar() {
    if (_bar) return _bar;

    _bar = document.createElement('div');
    _bar.id = 'bulkActionBar';
    _bar.setAttribute('aria-live', 'polite');
    _bar.innerHTML = `
      <div class="bulk-bar-inner">
        <span class="bulk-bar-label">
          <i class="bi bi-check2-square me-2"></i>
          <span id="bulkBarCount">0</span> selected
        </span>
        <div class="d-flex align-items-center gap-2">
          <button type="button" class="btn btn-sm btn-light" id="bulkClearBtn">
            <i class="bi bi-x-lg me-1"></i>Clear
          </button>
          <button type="button" class="btn btn-sm btn-danger fw-semibold" id="bulkDeleteBtn">
            <i class="bi bi-trash3-fill me-1"></i>Delete <span id="bulkDeleteCount">0</span>
          </button>
        </div>
      </div>`;
    document.body.appendChild(_bar);

    document.getElementById('bulkClearBtn').addEventListener('click', _clearAll);
    document.getElementById('bulkDeleteBtn').addEventListener('click', _confirmDelete);
    return _bar;
  }

  function _showBar(count, url, ids) {
    _currentUrl = url;
    _currentIds = ids;
    const bar = _getBar();
    document.getElementById('bulkBarCount').textContent    = count;
    document.getElementById('bulkDeleteCount').textContent = count;
    bar.classList.add('bulk-bar-visible');
  }

  function _hideBar() {
    if (_bar) _bar.classList.remove('bulk-bar-visible');
  }

  function _clearAll() {
    document.querySelectorAll('table[data-bulk-url]').forEach(t => {
      t.querySelectorAll('[data-bulk-item]').forEach(cb => { cb.checked = false; });
      const all = t.querySelector('[data-bulk-select-all]');
      if (all) { all.checked = false; all.indeterminate = false; }
    });
    _hideBar();
  }

  async function _confirmDelete() {
    const count = _currentIds.length;
    if (!count) return;
    const ok = await SA.confirm({
      title:   `Delete ${count} item${count !== 1 ? 's' : ''}`,
      message: `Permanently delete ${count} selected item${count !== 1 ? 's' : ''}? This cannot be undone.`,
      type:    'danger',
      okText:  `Delete ${count}`,
    });
    if (!ok) return;

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = _currentUrl;
    form.style.display = 'none';

    const csrfInput = document.createElement('input');
    csrfInput.type  = 'hidden';
    csrfInput.name  = 'csrf_token';
    csrfInput.value = (typeof csrfToken !== 'undefined') ? csrfToken : '';
    form.appendChild(csrfInput);

    _currentIds.forEach(id => {
      const inp = document.createElement('input');
      inp.type  = 'hidden';
      inp.name  = 'ids';
      inp.value = id;
      form.appendChild(inp);
    });

    document.body.appendChild(form);
    form.submit();
  }

  /* ── Per-table init ────────────────────────────────────────────────── */
  function _initTable(table) {
    const url   = table.dataset.bulkUrl  || '';
    const allCb = table.querySelector('[data-bulk-select-all]');

    function _items() {
      return Array.from(table.querySelectorAll('[data-bulk-item]'));
    }

    function _syncBar() {
      const checked = _items().filter(cb => cb.checked);
      if (checked.length > 0) {
        _showBar(checked.length, url, checked.map(cb => cb.value));
      } else {
        /* Only hide if no other table has selection */
        const anyChecked = Array.from(
          document.querySelectorAll('table[data-bulk-url] [data-bulk-item]:checked')
        );
        if (!anyChecked.length) _hideBar();
      }
    }

    function _syncSelectAll() {
      if (!allCb) return;
      const items   = _items();
      const checked = items.filter(cb => cb.checked);
      allCb.checked       = items.length > 0 && checked.length === items.length;
      allCb.indeterminate = checked.length > 0 && checked.length < items.length;
    }

    /* Select-all toggling rows */
    if (allCb) {
      allCb.addEventListener('change', function () {
        _items().forEach(cb => { cb.checked = this.checked; });
        _syncBar();
      });
    }

    /* Individual row checkbox */
    table.addEventListener('change', function (e) {
      if (!e.target.matches('[data-bulk-item]')) return;
      _syncSelectAll();
      _syncBar();
    });

    /* Clicking a row highlights it */
    table.addEventListener('change', function (e) {
      if (!e.target.matches('[data-bulk-item]')) return;
      const row = e.target.closest('tr');
      if (row) row.classList.toggle('bulk-row-selected', e.target.checked);
    });
  }

  /* ── Boot ──────────────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table[data-bulk-url]').forEach(_initTable);
  });
})();
