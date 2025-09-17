document.addEventListener('DOMContentLoaded', () => {
    // --- DOM ELEMENT SELECTORS ---
    const vitalsForm = document.getElementById('vitals-form');
    const mealForm = document.getElementById('meal-form');
    const photoInput = document.getElementById('photo');
    const imagePreview = document.getElementById('image-preview');
    const analyzeButton = document.getElementById('analyze-button');
    const mealStatusDiv = document.getElementById('meal-status');
    const mealResultDiv = document.getElementById('meal-result');
    const vitalsTableBody = document.querySelector('#vitals-table tbody');
    let vitalsChart;
    const chartCanvas = document.getElementById('vitalsChart').getContext('2d');

    // --- CHART & VITALS FUNCTIONS (Unchanged) ---
    // ... (initializeChart and fetchAndRenderVitals functions remain the same) ...
    function initializeChart() { if (vitalsChart) { vitalsChart.destroy(); } vitalsChart = new Chart(chartCanvas, { type: 'line', data: { labels: [], datasets: [ { label: 'Weight (kg)', data: [], borderColor: 'rgba(255, 99, 132, 1)', backgroundColor: 'rgba(255, 99, 132, 0.2)', fill: false, tension: 0.1 }, { label: 'Body Fat %', data: [], borderColor: 'rgba(54, 162, 235, 1)', backgroundColor: 'rgba(54, 162, 235, 0.2)', fill: false, tension: 0.1 }, { label: 'Muscle Mass (kg)', data: [], borderColor: 'rgba(75, 192, 192, 1)', backgroundColor: 'rgba(75, 192, 192, 0.2)', fill: false, tension: 0.1 } ] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { type: 'time', time: { unit: 'day', tooltipFormat: 'MMM dd, yyyy' }, title: { display: true, text: 'Date' } }, y: { beginAtZero: false, title: { display: true, text: 'Value' } } } } }); }
    async function fetchAndRenderVitals() { try { const response = await fetch('/api/vitals'); if (!response.ok) throw new Error('Network response was not ok'); const data = await response.json(); vitalsTableBody.innerHTML = ''; const labels = []; const weightData = []; const bodyFatData = []; const muscleMassData = []; data.forEach(entry => { const row = document.createElement('tr'); const formattedDate = new Date(entry.date).toLocaleDateString(); row.innerHTML = `<td>${formattedDate}</td><td>${entry.weight}</td><td>${entry.body_fat_percentage}</td><td>${entry.muscle_mass}</td>`; vitalsTableBody.appendChild(row); labels.push(entry.date); weightData.push(entry.weight); bodyFatData.push(entry.body_fat_percentage); muscleMassData.push(entry.muscle_mass); }); vitalsChart.data.labels = labels; vitalsChart.data.datasets[0].data = weightData; vitalsChart.data.datasets[1].data = bodyFatData; vitalsChart.data.datasets[2].data = muscleMassData; vitalsChart.update(); } catch (error) { console.error('Error fetching vitals:', error); alert('Failed to load vitals data.'); } }
    vitalsForm.addEventListener('submit', async (e) => { e.preventDefault(); const formData = { name: document.getElementById('name').value, age: parseInt(document.getElementById('age').value), weight: parseFloat(document.getElementById('weight').value), bmi: parseFloat(document.getElementById('bmi').value), body_fat_percentage: parseFloat(document.getElementById('body_fat_percentage').value), skeletal_muscle_percentage: parseFloat(document.getElementById('skeletal_muscle_percentage').value), fat_free_mass: parseFloat(document.getElementById('fat_free_mass').value), subcutaneous_fat: parseFloat(document.getElementById('subcutaneous_fat').value), visceral_fat: parseInt(document.getElementById('visceral_fat').value), body_water_percentage: parseFloat(document.getElementById('body_water_percentage').value), muscle_mass: parseFloat(document.getElementById('muscle_mass').value), bone_mass: parseFloat(document.getElementById('bone_mass').value), protein_percentage: parseFloat(document.getElementById('protein_percentage').value), bmr: parseInt(document.getElementById('bmr').value), metabolic_age: parseInt(document.getElementById('metabolic_age').value), }; try { const response = await fetch('/api/vitals', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) }); if (!response.ok) throw new Error('Failed to add vitals'); vitalsForm.reset(); fetchAndRenderVitals(); } catch (error) { console.error('Error submitting vitals:', error); alert('An error occurred. Please try again.'); } });

    // --- HELPER FUNCTION FOR DISPLAYING STATUS ---
    function showStatus(message, isError = false) {
        mealStatusDiv.textContent = message;
        mealStatusDiv.className = 'status-message'; // Reset classes
        mealStatusDiv.classList.add(isError ? 'error' : 'info');
        mealStatusDiv.classList.remove('hidden');
    }

    // --- MEAL FORM EVENT LISTENERS ---
    photoInput.addEventListener('change', () => {
        const file = photoInput.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
                imagePreview.classList.remove('hidden');
            };
            reader.readAsDataURL(file);
            mealStatusDiv.classList.add('hidden'); // Hide any previous errors
            mealResultDiv.classList.add('hidden');
        }
    });

    mealForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // This is the crucial fix! Prevents page reload.

        if (photoInput.files.length === 0) {
            showStatus('Please select an image file first.', true);
            return;
        }

        // 1. Prepare for submission
        analyzeButton.disabled = true;
        mealResultDiv.classList.add('hidden');
        showStatus('Uploading image...', false);

        // 2. Use FormData to correctly handle the file
        const formData = new FormData();
        formData.append('photo', photoInput.files[0]);

        try {
            showStatus('Analyzing with AI... this may take a moment.', false);
            
            const response = await fetch('/api/meal', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (result.status !== 'success') {
                // Display the specific error from the backend
                throw new Error(result.message || 'Analysis failed due to an unknown error.');
            }
            
            // 3. Display successful results
            mealStatusDiv.classList.add('hidden');
            document.getElementById('food-items').textContent = result.food_items.join(', ');
            const nutritionDiv = document.getElementById('nutrition-info');
            
            // Build HTML for nutrition display with breakdown if available
            let nutritionHTML = `
                <h4>Total Nutrition:</h4>
                <p><strong>Calories:</strong> ${result.nutrition.calories.toFixed(0)} kcal</p>
                <p><strong>Protein:</strong> ${result.nutrition.protein.toFixed(1)} g</p>
                <p><strong>Fat:</strong> ${result.nutrition.fat.toFixed(1)} g</p>
                <p><strong>Carbs:</strong> ${result.nutrition.carbohydrates.toFixed(1)} g</p>
            `;
            
            // Add breakdown if available
            if (result.breakdown && result.breakdown.length > 0) {
                nutritionHTML += `
                    <details style="margin-top: 15px;">
                        <summary style="cursor: pointer; font-weight: bold;">View Detailed Breakdown</summary>
                        <div style="margin-top: 10px; padding-left: 20px;">
                `;
                
                result.breakdown.forEach(item => {
                    nutritionHTML += `
                        <div style="margin-bottom: 10px; padding: 10px; background: #f5f5f5; border-radius: 5px;">
                            <strong>${item.food}</strong><br>
                            <span style="font-size: 0.9em; color: #666;">
                                Calories: ${item.nutrition.calories.toFixed(0)} kcal | 
                                Protein: ${item.nutrition.protein.toFixed(1)}g | 
                                Fat: ${item.nutrition.fat.toFixed(1)}g | 
                                Carbs: ${item.nutrition.carbohydrates.toFixed(1)}g
                            </span>
                        </div>
                    `;
                });
                
                nutritionHTML += `
                        </div>
                        <p style="margin-top: 10px; font-size: 0.85em; color: #666;">
                            <em>Note: Estimates based on 150g serving size per item. Actual values may vary.</em>
                        </p>
                    </details>
                `;
            }
            
            nutritionDiv.innerHTML = nutritionHTML;
            mealResultDiv.classList.remove('hidden');

        } catch (error) {
            console.error('Error analyzing meal:', error);
            showStatus(`Error: ${error.message}`, true); // Show the detailed error to the user
        } finally {
            // 4. Re-enable the button regardless of success or failure
            analyzeButton.disabled = false;
        }
    });

    // --- INITIALIZATION ---
    initializeChart();
    fetchAndRenderVitals();
});
