(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
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
  });

  document.body.addEventListener("htmx:responseError", function () {
    window.alert("Não foi possível concluir. Verifique a conexão e tente novamente.");
  });
})();
