(function () {
  var forms = Array.prototype.slice.call(document.querySelectorAll("form"));
  forms.forEach(function (form) {
    var requiredFields = requiredControls(form);
    if (!requiredFields.length) {
      return;
    }

    var managedSubmitButtons = submitButtons(form).filter(function (button) {
      return !button.disabled && !button.hasAttribute("data-product-edit-submit")
        && !button.hasAttribute("data-supplier-batch-submit")
        && !button.hasAttribute("data-upload-preview-confirm");
    });

    form.addEventListener("submit", function (event) {
      markInvalidControls(form);
      if (!form.checkValidity()) {
        event.preventDefault();
        focusFirstInvalidControl(form);
      }
    });

    requiredFields.forEach(function (field) {
      field.addEventListener("input", function () {
        updateControlValidationState(field);
        updateManagedSubmitButtons();
      });
      field.addEventListener("change", function () {
        updateControlValidationState(field);
        updateManagedSubmitButtons();
      });
      field.addEventListener("blur", function () {
        markControlGroupValidated(field);
        updateControlValidationState(field);
      });
      updateControlValidationState(field);
    });

    updateManagedSubmitButtons();

    function updateManagedSubmitButtons() {
      if (!managedSubmitButtons.length) {
        return;
      }
      var ready = formRequiredFieldsReady(form);
      managedSubmitButtons.forEach(function (button) {
        button.disabled = !ready;
      });
    }
  });

  function requiredControls(form) {
    return Array.prototype.slice.call(
      form.querySelectorAll("input[required], select[required], textarea[required]")
    ).filter(function (field) {
      return field.type !== "hidden" && !field.disabled;
    });
  }

  function submitButtons(form) {
    return Array.prototype.slice.call(
      form.querySelectorAll('button[type="submit"], input[type="submit"]')
    );
  }

  function formRequiredFieldsReady(form) {
    return requiredControls(form).every(function (field) {
      if (field.type === "radio") {
        return Boolean(form.querySelector('input[name="' + cssEscape(field.name) + '"]:checked'));
      }
      if (field.type === "checkbox") {
        return field.checked;
      }
      return Boolean((field.value || "").trim()) && field.checkValidity();
    });
  }

  function markInvalidControls(form) {
    requiredControls(form).forEach(function (field) {
      markControlGroupValidated(field);
      updateControlValidationState(field);
    });
  }

  function markControlGroupValidated(field) {
    if (field.type !== "radio") {
      field.classList.add("was-validated");
      return;
    }
    Array.prototype.slice.call(
      field.form.querySelectorAll('input[name="' + cssEscape(field.name) + '"]')
    ).forEach(function (control) {
      control.classList.add("was-validated");
    });
  }

  function updateControlValidationState(field) {
    var fields = field.type === "radio"
      ? Array.prototype.slice.call(field.form.querySelectorAll('input[name="' + cssEscape(field.name) + '"]'))
      : [field];
    var invalid = !field.checkValidity();
    var shouldShowInvalid = fields.some(function (control) {
      return control.classList.contains("was-validated");
    });
    fields.forEach(function (control) {
      control.classList.toggle("is-invalid", shouldShowInvalid && invalid);
    });
  }

  function focusFirstInvalidControl(form) {
    var invalid = form.querySelector(".is-invalid, :invalid");
    if (invalid && typeof invalid.focus === "function") {
      invalid.focus();
    }
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/"/g, '\\"');
  }
})();

(function () {
  var storageKey = "gts_operator_name";
  var operatorInputs = Array.prototype.slice.call(
    document.querySelectorAll('input[name="operator_name"]')
  );

  if (!operatorInputs.length || !window.localStorage) {
    return;
  }

  var savedName = window.localStorage.getItem(storageKey);
  operatorInputs.forEach(function (operatorInput) {
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
  });
})();

(function () {
  var menuButton = document.querySelector("[data-operator-menu-button]");
  var menu = document.querySelector(".operator-menu");
  var modal = document.querySelector("[data-operator-modal]");
  var modalInput = document.querySelector("[data-operator-modal-input]");
  var openButton = document.querySelector("[data-operator-modal-open]");
  var closeButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-operator-modal-close]")
  );

  if (menuButton && menu) {
    menuButton.addEventListener("click", function () {
      var isOpen = menu.classList.toggle("is-open");
      menuButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    document.addEventListener("click", function (event) {
      if (!menu.contains(event.target)) {
        menu.classList.remove("is-open");
        menuButton.setAttribute("aria-expanded", "false");
      }
    });
  }

  if (!modal || !openButton) {
    return;
  }

  openButton.addEventListener("click", function () {
    if (menu) {
      menu.classList.remove("is-open");
    }
    if (menuButton) {
      menuButton.setAttribute("aria-expanded", "false");
    }
    modal.hidden = false;
    if (modalInput) {
      modalInput.focus();
      modalInput.select();
    }
  });

  closeButtons.forEach(function (button) {
    button.addEventListener("click", closeModal);
  });

  modal.addEventListener("click", function (event) {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.hidden) {
      closeModal();
    }
  });

  function closeModal() {
    modal.hidden = true;
    if (menuButton) {
      menuButton.focus();
    }
  }
})();

(function () {
  var form = document.querySelector("[data-product-edit-form]");
  if (!form) {
    return;
  }

  var fields = Array.prototype.slice.call(
    form.querySelectorAll("[data-product-edit-field]")
  );
  var submitButton = form.querySelector("[data-product-edit-submit]");
  if (!fields.length || !submitButton) {
    return;
  }

  fields.forEach(function (field) {
    field.addEventListener("input", updateSubmitState);
  });
  updateSubmitState();

  function updateSubmitState() {
    submitButton.disabled = !fields.some(fieldChanged) || !requiredFieldsReady(form);
  }

  function fieldChanged(field) {
    return field.value.trim() !== (field.getAttribute("data-original-value") || "").trim();
  }

  function requiredFieldsReady(formElement) {
    var requiredFields = Array.prototype.slice.call(
      formElement.querySelectorAll("input[required], select[required], textarea[required]")
    );
    return requiredFields.every(function (field) {
      return Boolean((field.value || "").trim()) && field.checkValidity();
    });
  }
})();

(function () {
  var streamContainer = document.querySelector("[data-upload-preview-stream]");
  if (!streamContainer || !window.EventSource) {
    return;
  }

  var streamUrl = streamContainer.getAttribute("data-upload-preview-stream");
  var previewTokenInput = document.querySelector('input[name="token"]');
  var previewToken = previewTokenInput ? previewTokenInput.value : "";
  var tableBody = document.querySelector("[data-upload-preview-body]");
  var headerRow = document.querySelector("[data-upload-preview-header]");
  var confirmButton = document.querySelector("[data-upload-preview-confirm]");
  var confirmSpinner = document.querySelector("[data-upload-preview-confirm-spinner]");
  var progressText = document.querySelector("[data-upload-preview-progress]");
  var rowElements = {};
  var rowCount = 0;
  var warningsVisible = false;
  var initialRowCleared = false;
  var renderQueue = [];
  var renderQueueRunning = false;
  var renderStepDelayMs = 12;
  var eventSource = new EventSource(streamUrl);

  eventSource.addEventListener("loading", function (event) {
    var data = JSON.parse(event.data);
    enqueueRender(function () {
      clearInitialRow();
      rowElements[data.row_number] = renderLoadingRow(data.row_number);
      tableBody.appendChild(rowElements[data.row_number]);
      if (progressText) {
        progressText.textContent = "正在读取第 " + data.row_number + " 行...";
      }
    });
  });

  eventSource.addEventListener("row", function (event) {
    var row = JSON.parse(event.data);
    enqueueRender(function () {
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
        progressText.textContent = "已读取 " + rowCount + " 行...";
      }
    });
  });

  eventSource.addEventListener("complete", function (event) {
    var data = JSON.parse(event.data);
    eventSource.close();
    enqueueRender(function () {
      stopConfirmLoading();
      if (data.has_supplier_pending && previewToken) {
        if (progressText) {
          progressText.textContent = "请先处理供应商匹配，正在打开匹配页面...";
          progressText.classList.add("status-warning");
        }
        window.location.href = "/upload/preview/" + previewToken;
        return;
      }
      if (confirmButton && data.has_errors) {
        confirmButton.disabled = true;
      } else if (confirmButton) {
        confirmButton.disabled = false;
      }
      if (progressText) {
        if (data.has_errors) {
          progressText.textContent = "预览有错误，请修改 Excel 后再导入。";
          progressText.classList.add("status-warning");
        } else {
          progressText.textContent = "预览完成：" + data.row_count + " 行。";
        }
      }
    });
  });

  eventSource.addEventListener("preview_error", function (event) {
    eventSource.close();
    cancelRenderQueue();
    stopConfirmLoading();
    if (progressText) {
      var data = JSON.parse(event.data);
      progressText.textContent = data.message || "预览加载失败。";
      progressText.classList.add("status-warning");
    }
  });

  eventSource.onerror = function () {
    eventSource.close();
    cancelRenderQueue();
    stopConfirmLoading();
    if (progressText) {
      progressText.textContent = "预览加载失败。";
      progressText.classList.add("status-warning");
    }
  };

  function clearInitialRow() {
    if (!initialRowCleared) {
      tableBody.textContent = "";
      initialRowCleared = true;
    }
  }

  function stopConfirmLoading() {
    if (confirmSpinner) {
      confirmSpinner.classList.add("is-hidden");
    }
  }

  function enqueueRender(action) {
    renderQueue.push(action);
    if (!renderQueueRunning) {
      renderQueueRunning = true;
      window.setTimeout(processRenderQueue, 0);
    }
  }

  function cancelRenderQueue() {
    renderQueue = [];
    renderQueueRunning = false;
  }

  function processRenderQueue() {
    var action = renderQueue.shift();
    if (action) {
      action();
    }
    if (renderQueue.length) {
      window.setTimeout(processRenderQueue, renderStepDelayMs);
    } else {
      renderQueueRunning = false;
    }
  }

  function renderLoadingRow(rowNumber) {
    var tr = document.createElement("tr");
    tr.className = "preview-loading-row";
    appendCell(tr, rowNumber);
    var statusCell = appendCell(tr, "");
    statusCell.className = "status-cell";
    var spinner = document.createElement("span");
    spinner.className = "loading-icon";
    spinner.setAttribute("aria-hidden", "true");
    spinner.title = "读取中";
    statusCell.appendChild(spinner);
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
    statusCell.className = "status-cell";
    statusCell.appendChild(createStatusIcon(row, hasWarnings));
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
    th.textContent = "提醒";
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
    appendParagraphs(td, row.quotation_warnings || [], "price-warning");
    (row.required_choices || []).forEach(function (choice) {
      appendRequiredChoice(td, row.row_number, choice);
    });
    (row.product_changes || []).forEach(function (change) {
      var label = document.createElement("label");
      label.className = "checkbox-line";
      var input = document.createElement("input");
      input.type = "checkbox";
      input.name = "update_product__" + row.row_number + "__" + change.field;
      label.appendChild(input);
      label.appendChild(
        document.createTextNode(
          ' 更新' + productChangeLabel(change.field) + '："'
          + (change.existing_with_source || change.existing) + '" → "' + change.incoming + '"'
        )
      );
      td.appendChild(label);
    });
    return td;
  }

  function appendRequiredChoice(container, rowNumber, choice) {
    var wrapper = document.createElement("div");
    wrapper.className = "required-choice-control";
    var message = document.createElement("p");
    message.className = "price-warning";
    message.textContent = choice.label + "：" + choice.message;
    wrapper.appendChild(message);
    wrapper.appendChild(createChoiceRadio(rowNumber, choice.field, "old", "保留旧值"));
    wrapper.appendChild(createChoiceRadio(rowNumber, choice.field, "new", "使用新值"));
    container.appendChild(wrapper);
  }

  function createChoiceRadio(rowNumber, field, value, text) {
    var label = document.createElement("label");
    label.className = "radio-line";
    var input = document.createElement("input");
    input.type = "radio";
    input.name = "required_choice__" + rowNumber + "__" + field;
    input.value = value;
    input.required = true;
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + text));
    return label;
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

  function createStatusIcon(row, hasWarnings) {
    var status = document.createElement("span");
    status.className = "status-icon";
    if (row.errors && row.errors.length) {
      status.className += " status-warning";
      status.textContent = "×";
      status.title = "失败";
      status.setAttribute("aria-label", "失败");
      return status;
    }
    if (hasWarnings) {
      status.className += " status-review";
      status.textContent = "!";
      status.title = "需确认";
      status.setAttribute("aria-label", "需确认");
      return status;
    }
    status.className += " status-ready";
    status.textContent = "✓";
    status.title = "可导入";
    status.setAttribute("aria-label", "可导入");
    return status;
  }

  function productChangeLabel(field) {
    if (field === "oem") {
      return "OEM";
    }
    if (field === "description") {
      return "英文描述";
    }
    if (field === "chinese_description") {
      return "品名";
    }
    return field;
  }

  function rowHasWarnings(row) {
    return Boolean(
        (row.errors && row.errors.length) ||
        (row.warnings && row.warnings.length) ||
        (row.quotation_warnings && row.quotation_warnings.length) ||
        (row.required_choices && row.required_choices.length) ||
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
    if (!confirm("确认导入？系统会新增报价记录。")) {
      event.preventDefault();
    }
  });
})();

(function () {
  var batchForm = document.querySelector("[data-supplier-batch-form]");
  if (batchForm) {
    var batchSubmit = batchForm.querySelector("[data-supplier-batch-submit]");
    batchForm.addEventListener("input", updateBatchState);
    batchForm.addEventListener("change", updateBatchState);
    updateBatchState();

    function updateBatchState() {
      if (!batchSubmit) {
        return;
      }
      batchSubmit.disabled = !batchFormReady(batchForm);
    }
  }

  var supplierForms = Array.prototype.slice.call(
    document.querySelectorAll("[data-supplier-link-form], [data-supplier-create-form]")
  );

  supplierForms.forEach(function (form) {
    var submitButton = form.querySelector(
      "[data-supplier-link-submit], [data-supplier-create-submit]"
    );
    if (!submitButton) {
      return;
    }
    form.addEventListener("input", updateState);
    form.addEventListener("change", updateState);
    updateState();

    function updateState() {
      submitButton.disabled = !formIsReady(form);
    }
  });

  function formIsReady(form) {
    var requiredFields = Array.prototype.slice.call(
      form.querySelectorAll("input[required], select[required], textarea[required]")
    );
    return requiredFields.every(function (field) {
      if (field.type === "radio") {
        return Boolean(form.querySelector('input[name="' + field.name + '"]:checked'));
      }
      return Boolean((field.value || "").trim());
    });
  }

  function batchFormReady(form) {
    var rows = Array.prototype.slice.call(form.querySelectorAll("[data-supplier-batch-row]"));
    return rows.every(function (row) {
      var action = row.querySelector('input[name^="action__"]:checked')
        || row.querySelector('input[type="hidden"][name^="action__"]');
      if (!action || !action.value) {
        return false;
      }
      if (action.value === "existing" || action.value === "ambiguous") {
        var supplier = row.querySelector('select[name^="supplier_id__"], input[type="radio"][name^="supplier_id__"]:checked');
        return Boolean(supplier && supplier.value);
      }
      if (action.value === "create") {
        var shortName = row.querySelector('input[name^="supplier_short_name__"]');
        return Boolean(shortName && shortName.value.trim());
      }
      return false;
    });
  }
})();
