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
