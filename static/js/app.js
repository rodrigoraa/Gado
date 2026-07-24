(function () {
  "use strict";

  function isoParaBrasil(valor) {
    var partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(valor || "");
    return partes ? partes[3] + "/" + partes[2] + "/" + partes[1] : valor;
  }

  function brasilParaIso(valor) {
    var partes = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(valor || "");
    if (!partes) {
      return "";
    }
    var iso = partes[3] + "-" + partes[2] + "-" + partes[1];
    var data = new Date(iso + "T12:00:00");
    return !Number.isNaN(data.getTime()) &&
      data.getFullYear() === Number(partes[3]) &&
      data.getMonth() + 1 === Number(partes[2]) &&
      data.getDate() === Number(partes[1]) ? iso : "";
  }

  function aplicarMascaraData(valor) {
    var numeros = valor.replace(/\D/g, "").slice(0, 8);
    if (numeros.length > 4) {
      return numeros.slice(0, 2) + "/" + numeros.slice(2, 4) + "/" + numeros.slice(4);
    }
    if (numeros.length > 2) {
      return numeros.slice(0, 2) + "/" + numeros.slice(2);
    }
    return numeros;
  }

  function melhorarCamposData() {
    document.querySelectorAll(
      ".form-card input[type='date'], .confirm-card input[type='date']"
    ).forEach(function (campo) {
      if (campo.dataset.dateEnhanced) {
        return;
      }
      campo.dataset.dateEnhanced = "true";
      var valorInicial = campo.value;
      campo.type = "text";
      campo.inputMode = "numeric";
      campo.placeholder = "DD/MM/AAAA";
      campo.autocomplete = "off";
      campo.value = isoParaBrasil(valorInicial);

      var controle = document.createElement("div");
      controle.className = "date-field-control";
      campo.parentNode.insertBefore(controle, campo);
      controle.appendChild(campo);

      var calendario = document.createElement("input");
      calendario.type = "date";
      calendario.className = "date-calendar-native";
      calendario.tabIndex = -1;
      calendario.setAttribute("aria-hidden", "true");
      calendario.value = brasilParaIso(campo.value);

      var botao = document.createElement("button");
      botao.type = "button";
      botao.className = "date-calendar-button";
      botao.setAttribute("aria-label", "Abrir calendário");
      botao.textContent = "▦";

      campo.addEventListener("input", function () {
        campo.value = aplicarMascaraData(campo.value);
        calendario.value = brasilParaIso(campo.value);
      });
      calendario.addEventListener("change", function () {
        campo.value = isoParaBrasil(calendario.value);
        campo.dispatchEvent(new Event("change", { bubbles: true }));
      });
      botao.addEventListener("click", function () {
        calendario.value = brasilParaIso(campo.value);
        if (typeof calendario.showPicker === "function") {
          calendario.showPicker();
        } else {
          calendario.click();
        }
      });

      controle.appendChild(botao);
      controle.appendChild(calendario);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    melhorarCamposData();
    document.querySelectorAll("form").forEach(function (form) {
      form.addEventListener("submit", function () {
        var button = form.querySelector("button[type='submit']");
        if (button && !button.dataset.noLoading) {
          button.disabled = true;
          button.dataset.originalText = button.textContent;
          button.textContent = "Salvando…";
        }
      });
    });

    window.setTimeout(function () {
      document.querySelectorAll(".app-toast").forEach(function (toast) {
        toast.remove();
      });
    }, 6500);

    var menus = document.querySelectorAll(".user-menu, .mobile-more");

    document.addEventListener("click", function (event) {
      menus.forEach(function (menu) {
        if (menu.open && !menu.contains(event.target)) {
          menu.removeAttribute("open");
        }
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        menus.forEach(function (menu) {
          menu.removeAttribute("open");
        });
      }
    });

    document.querySelectorAll(".mobile-more-menu a").forEach(function (link) {
      link.addEventListener("click", function () {
        link.closest("details").removeAttribute("open");
      });
    });
  });

  document.body.addEventListener("htmx:responseError", function () {
    window.alert("Não foi possível concluir. Verifique a conexão e tente novamente.");
  });
})();
