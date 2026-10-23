// JavaScript secukupnya: baris item dinamis pada form PR dan hitung total.
(function () {
  function rupiah(n) {
    return "Rp " + Math.round(n).toLocaleString("id-ID");
  }
  function num(v) {
    v = (v || "").toString().trim();
    if (!v) return 0;
    if (v.indexOf(",") > -1 && v.indexOf(".") > -1) { v = v.replace(/\./g, "").replace(",", "."); }
    else if (/^\d{1,3}(\.\d{3})+$/.test(v)) { v = v.replace(/\./g, ""); }
    else { v = v.replace(",", "."); }
    var x = parseFloat(v);
    return isNaN(x) ? 0 : x;
  }
  var body = document.getElementById("item-rows");
  if (!body) return;
  var template = document.getElementById("item-row-template");
  function recalc() {
    var total = 0;
    body.querySelectorAll("tr").forEach(function (tr) {
      var sub = num(tr.querySelector("[name=qty]").value) * num(tr.querySelector("[name=price]").value);
      tr.querySelector(".subtotal").textContent = rupiah(sub);
      total += sub;
    });
    var out = document.getElementById("grand-total");
    if (out) out.textContent = rupiah(total);
  }
  function addRow() {
    body.appendChild(template.content.firstElementChild.cloneNode(true));
    recalc();
  }
  document.getElementById("add-row").addEventListener("click", addRow);
  body.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-row")) { e.target.closest("tr").remove(); recalc(); }
  });
  body.addEventListener("change", function (e) {
    if (e.target.name === "item_id") {
      var opt = e.target.selectedOptions[0];
      var tr = e.target.closest("tr");
      if (opt && opt.dataset.price && !tr.querySelector("[name=price]").value) {
        tr.querySelector("[name=price]").value = opt.dataset.price;
      }
      var unit = tr.querySelector(".unit");
      if (unit) unit.textContent = opt && opt.dataset.unit ? opt.dataset.unit : "";
    }
    recalc();
  });
  body.addEventListener("input", recalc);
  if (!body.querySelector("tr")) addRow(); else recalc();
})();
