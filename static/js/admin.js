$(document).ready(function () {
    // Handle Add User Form Submission
    $("#addUserForm").submit(function (event) {
        event.preventDefault(); // Prevent default form submission

        let username = $("#username").val();
        let password = $("#password").val();
        let confirmPassword = $("#confirmPassword").val();
        let message = $("#message");

        message.html(''); // Clear previous messages

        if (password !== confirmPassword) {
            message.html('<div class="alert alert-danger">Passwords do not match.</div>');
            return;
        }

        // Validate password strength
        const passwordRegex = /^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
        if (!passwordRegex.test(password)) {
            message.html('<div class="alert alert-danger">Password must be at least 8 characters long, contain an uppercase letter, a number, and a special character.</div>');
            return;
        }

        $.ajax({
            type: "POST",
            url: "/admin/add_user",
            contentType: "application/json",
            data: JSON.stringify({ username: username, password: password }),
            success: function (response) {
                message.html(`<div class="alert alert-success">${response.message}</div>`);
                $("#addUserForm")[0].reset(); // Clear form fields
                loadUsers(); // Refresh the user list
            },
            error: function (xhr) {
                message.html(`<div class="alert alert-danger">${xhr.responseJSON.message}</div>`);
            }
        });
    });

    // Load users when the page loads
    loadUsers();

    // Function to load and display users
    function loadUsers() {
        $.get("/admin/get_users", function (data) {
            let userList = $("#userList");
            userList.empty();

            data.users.forEach(user => {
                let removeBtn = "";

                // Only show remove button if not admin
                if (user.toLowerCase() !== "vcrt_admin") {
                    console.log(user);
                    removeBtn = `<button class="btn btn-danger btn-sm remove-user" data-username="${user}">Remove</button>`;
                }

                userList.append(`
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        ${user}
                        ${removeBtn}
                    </li>
                `);
            });
        });
    }


    // Handle user removal with event delegation
    $("#userList").on("click", ".remove-user", function () {
        let username = $(this).data("username");

        $.ajax({
            type: "POST",
            url: "/admin/remove_user",
            contentType: "application/json",
            data: JSON.stringify({ username: username }),
            success: function (response) {
                loadUsers(); // Refresh the user list
            },
            error: function (xhr) {
                alert(xhr.responseJSON.message);
            }
        });
    });

    // Filter user list based on search input
    $("#userSearch").on("input", function () {
        const searchTerm = $(this).val().toLowerCase();
        $("#userList .list-group-item").each(function () {
            const username = $(this).text().trim().toLowerCase();
            $(this).toggle(username.includes(searchTerm));
        });
    });
});
