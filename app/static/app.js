(function () {
  var storageKey = "gts_operator_name";
  var operatorInput = document.querySelector('input[name="operator_name"]');

  if (!operatorInput || !window.localStorage) {
    return;
  }

  var savedName = window.localStorage.getItem(storageKey);
  if (savedName && !operatorInput.value) {
    operatorInput.value = savedName;
  }

  operatorInput.addEventListener("input", function () {
    var value = operatorInput.value.trim();
    if (value) {
      window.localStorage.setItem(storageKey, value);
    }
  });

  var form = operatorInput.form;
  if (form) {
    form.addEventListener("submit", function () {
      var value = operatorInput.value.trim();
      if (value) {
        window.localStorage.setItem(storageKey, value);
      }
    });
  }
})();
