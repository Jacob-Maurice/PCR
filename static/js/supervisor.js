

    // Adjust the height of a textarea as the user types
    function autoGrow(element) {
        element.style.height = "auto";
        element.style.height = (element.scrollHeight) + "px";
    }

   








// Drawing On picture
const canvas = document.getElementById("injuryCanvas");
const ctx = canvas.getContext("2d");

// Get the image from the hidden img element
const imageElement = document.getElementById("injuryImage");
const image = new Image();
image.src = imageElement.src;

// Draw the image onto the canvas when it's loaded
image.onload = function() {
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
};

// Handle canvas click event to mark the injury location
canvas.addEventListener("click", function(e) {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Draw a red circle at the clicked coordinates
    drawCircle(x, y);

    // Send the coordinates to the Flask backend
    saveCoordinates(x, y);
});

// Function to draw a circle on the canvas
function drawCircle(x, y) {
    ctx.beginPath();
    ctx.arc(x, y, 10, 0, 2 * Math.PI);
    ctx.fillStyle = "red";
    ctx.fill();
}

// Function to save coordinates to the Flask backend
function saveCoordinates(x, y) {
    fetch("/save_coordinates", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ x: x, y: y })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Network response was not ok");
        }
        return response.json();
    })
    .then(data => console.log(data.message))
    .catch(error => console.error("Error saving coordinates:", error));
}

// Handle resetting the image
document.addEventListener('DOMContentLoaded', () => {
    // Get the reset button, the image element, and the canvas
    const resetImageBtn = document.getElementById('resetImageBtn');
    const injuryImage = document.getElementById('injuryImage');
    const canvas = document.getElementById('injuryCanvas');
    const ctx = canvas.getContext('2d');

    // Store the original image source in a variable
    const originalImageSrc = injuryImage.src;

    // Function to load and draw the image on the canvas
    function loadImageToCanvas(imageSrc) {
        const image = new Image();
        image.src = imageSrc;

        image.onload = function() {
            // Clear the canvas first before redrawing
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            // Draw the new image onto the canvas
            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        };
    }

    // Initially load the image onto the canvas
    loadImageToCanvas(injuryImage.src);

    // Reset button logic
    resetImageBtn.addEventListener('click', () => {
        // Reset the image source in the img element
        injuryImage.src = originalImageSrc;

        // Redraw the original image onto the canvas
        loadImageToCanvas(originalImageSrc);

        // Clear any drawn circles to maintain a fresh reset state
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    });
});



//
// Section for saving Data
//

document.getElementById("pcrForm").addEventListener("submit", async function (event) {
    event.preventDefault(); // Prevent the default form submission behavior

    let formData = new FormData(this); // Capture form data

    let jsonData = {};
    formData.forEach((value, key) => {
        jsonData[key] = value;
    });

    try {
        let response = await fetch("/submit_draft", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(jsonData),
        });

        let result = await response.json();
        alert(result.message); // Show success message
    } catch (error) {
        console.error("Error:", error);
        alert("Something went wrong!");
    }
});


