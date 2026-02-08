function openVehicle(id) {
  fetch('/vehicle/' + id)
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.text();
    })
    .then(html => {
      document.getElementById('vehicleModalContainer').innerHTML = html;
      var modalElement = document.getElementById('vehicleModal');
      var modal = new bootstrap.Modal(modalElement);
      modal.show();
    })
    .catch(err => {
      alert('Failed to load vehicle details: ' + err);
    });
}
