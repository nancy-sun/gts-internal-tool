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

(function () {
  var streamContainer = document.querySelector("[data-upload-preview-stream]");
  if (!streamContainer || !window.EventSource) {
    return;
  }

  var streamUrl = streamContainer.getAttribute("data-upload-preview-stream");
  var tableBody = document.querySelector("[data-upload-preview-body]");
  var headerRow = document.querySelector("[data-upload-preview-header]");
  var confirmButton = document.querySelector("[data-upload-preview-confirm]");
  var progressText = document.querySelector("[data-upload-preview-progress]");
  var rowElements = {};
  var rowCount = 0;
  var warningsVisible = false;
  var initialRowCleared = false;
  var eventSource = new EventSource(streamUrl);

  eventSource.addEventListener("loading", function (event) {
    var data = JSON.parse(event.data);
    clearInitialRow();
    rowElements[data.row_number] = renderLoadingRow(data.row_number);
    tableBody.appendChild(rowElements[data.row_number]);
  });

  eventSource.addEventListener("row", function (event) {
    var row = JSON.parse(event.data);
    clearInitialRow();
    rowCount += 1;
    if (rowHasWarnings(row)) {
      ensureWarningsColumn();
    }
    var rowElement = renderPreviewRow(row);
    if (rowElements[row.row_number]) {
      tableBody.replaceChild(rowElement, rowElements[row.row_number]);
    } else {
      tableBody.appendChild(rowElement);
    }
    rowElements[row.row_number] = rowElement;
    if (progressText) {
      progressText.textContent = "Loaded " + rowCount + " rows...";
    }
  });

  eventSource.addEventListener("complete", function (event) {
    var data = JSON.parse(event.data);
    eventSource.close();
    if (confirmButton && data.has_errors) {
      confirmButton.disabled = true;
    } else if (confirmButton) {
      confirmButton.disabled = false;
    }
    if (progressText) {
      if (data.has_errors) {
        progressText.textContent = "Preview has errors. Fix the Excel file before importing.";
        progressText.classList.add("status-warning");
      } else {
        progressText.textContent = "Preview ready: " + data.row_count + " rows.";
      }
    }
  });

  eventSource.addEventListener("preview_error", function (event) {
    eventSource.close();
    if (progressText) {
      var data = JSON.parse(event.data);
      progressText.textContent = data.message || "Preview loading failed.";
      progressText.classList.add("status-warning");
    }
  });

  eventSource.onerror = function () {
    eventSource.close();
    if (progressText) {
      progressText.textContent = "Preview loading failed.";
      progressText.classList.add("status-warning");
    }
  };

  function clearInitialRow() {
    if (!initialRowCleared) {
      tableBody.textContent = "";
      initialRowCleared = true;
    }
  }

  function renderLoadingRow(rowNumber) {
    var tr = document.createElement("tr");
    tr.className = "preview-loading-row";
    appendCell(tr, rowNumber);
    var statusCell = appendCell(tr, "");
    var spinner = document.createElement("span");
    spinner.className = "loading-icon";
    spinner.setAttribute("aria-hidden", "true");
    statusCell.appendChild(spinner);
    statusCell.appendChild(document.createTextNode(" Loading"));
    for (var i = 0; i < 7; i += 1) {
      appendCell(tr, "");
    }
    if (warningsVisible) {
      appendCell(tr, "");
    }
    return tr;
  }

  function renderPreviewRow(row) {
    var values = row.values || {};
    var tr = document.createElement("tr");
    tr.className = "preview-data-row";
    var hasWarnings = rowHasWarnings(row);
    appendCell(tr, row.row_number);
    var statusCell = appendCell(tr, "");
    var status = document.createElement("span");
    status.className =
      row.errors && row.errors.length ? "status-warning" : hasWarnings ? "status-review" : "status-ready";
    status.textContent = row.errors && row.errors.length ? "Failed" : hasWarnings ? "Review" : "Ready";
    statusCell.appendChild(status);
    appendCell(tr, values.gts_no || "");
    appendCell(tr, values.oem || "");
    appendCell(tr, values.chinese_description || "");
    appendCell(tr, values.factory || "");
    appendCell(tr, values.unit || "");
    appendCell(tr, formatCurrency(values.unit_price));
    appendCell(tr, values.expected_delivery || "");
    if (warningsVisible) {
      appendWarningsCell(tr, row);
    }
    return tr;
  }

  function ensureWarningsColumn() {
    if (warningsVisible) {
      return;
    }
    warningsVisible = true;
    var th = document.createElement("th");
    th.className = "warning-heading preview-warning-heading";
    th.textContent = "Warnings";
    headerRow.appendChild(th);
    Object.keys(rowElements).forEach(function (rowNumber) {
      appendCell(rowElements[rowNumber], "");
    });
  }

  function appendWarningsCell(tr, row) {
    var td = appendCell(tr, "");
    if (!rowHasWarnings(row)) {
      return td;
    }
    td.className = "warning-cell";
    appendParagraphs(td, row.errors || [], "error");
    appendParagraphs(td, row.warnings || [], "small-warning");
    if (row.factory_warning) {
      appendParagraphs(td, [row.factory_warning], "small-warning");
    }
    appendParagraphs(td, row.price_warnings || [], "price-warning");
    (row.product_changes || []).forEach(function (change) {
      var label = document.createElement("label");
      label.className = "checkbox-line";
      var input = document.createElement("input");
      input.type = "checkbox";
      input.name = "update_product__" + row.row_number + "__" + change.field;
      label.appendChild(input);
      label.appendChild(
        document.createTextNode(
          ' Update ' + change.field + ' from "' + change.existing + '" to "' + change.incoming + '"'
        )
      );
      td.appendChild(label);
    });
    return td;
  }

  function appendParagraphs(container, messages, className) {
    messages.forEach(function (message) {
      var p = document.createElement("p");
      p.className = className;
      p.textContent = message;
      container.appendChild(p);
    });
  }

  function appendCell(row, text) {
    var cell = document.createElement("td");
    cell.textContent = text == null ? "" : text;
    row.appendChild(cell);
    return cell;
  }

  function rowHasWarnings(row) {
    return Boolean(
      (row.errors && row.errors.length) ||
        (row.warnings && row.warnings.length) ||
        row.factory_warning ||
        (row.price_warnings && row.price_warnings.length) ||
        (row.product_changes && row.product_changes.length)
    );
  }

  function formatCurrency(value) {
    if (value === null || value === undefined || value === "") {
      return "";
    }
    var numeric = Number(value);
    if (Number.isNaN(numeric)) {
      return "";
    }
    return "¥" + numeric.toFixed(2);
  }
})();

(function () {
  var previewForm = document.querySelector("[data-upload-preview-form]");
  if (!previewForm) {
    return;
  }

  previewForm.addEventListener("submit", function (event) {
    if (!confirm("Confirm import? This will add quotation rows to the system.")) {
      event.preventDefault();
    }
  });
})();
