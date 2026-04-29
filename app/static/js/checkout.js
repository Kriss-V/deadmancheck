function startCheckout(plan) {
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '/billing/checkout?plan=' + plan;
  document.body.appendChild(form);
  form.submit();
}
