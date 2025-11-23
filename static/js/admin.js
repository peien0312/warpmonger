// Admin Dashboard JavaScript

let currentProduct = null;
let currentBlogPost = null;
let uploadedImages = [];

// ===== Initialization =====

document.addEventListener('DOMContentLoaded', () => {
    loadCategories();
    loadBlogPosts();
    setupImageUpload();
    setupForms();
    setupPreview();
});

// ===== Load Content =====

async function loadCategories() {
    try {
        const response = await fetch('/api/products');
        const data = await response.json();

        const categoriesMap = {};
        data.products.forEach(product => {
            if (!categoriesMap[product.category]) {
                categoriesMap[product.category] = [];
            }
            categoriesMap[product.category].push(product);
        });

        renderCategories(categoriesMap);
        updateCategoriesDatalist(Object.keys(categoriesMap));
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

function renderCategories(categoriesMap) {
    const container = document.getElementById('categories-list');
    container.innerHTML = '';

    Object.keys(categoriesMap).sort().forEach(category => {
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'category-section';

        const categoryHeader = document.createElement('div');
        categoryHeader.className = 'category-header';
        categoryHeader.textContent = category;
        categoryHeader.onclick = () => toggleCategory(category);

        const productsList = document.createElement('div');
        productsList.className = 'products-list';
        productsList.id = `category-${category}`;

        categoriesMap[category].forEach(product => {
            const productLink = document.createElement('a');
            productLink.className = 'product-link';
            productLink.textContent = product.title;
            productLink.href = '#';
            productLink.onclick = (e) => {
                e.preventDefault();
                editProduct(product.category, product.slug);
            };
            productsList.appendChild(productLink);
        });

        categoryDiv.appendChild(categoryHeader);
        categoryDiv.appendChild(productsList);
        container.appendChild(categoryDiv);
    });
}

function toggleCategory(category) {
    const list = document.getElementById(`category-${category}`);
    if (list.style.display === 'none') {
        list.style.display = 'block';
    } else {
        list.style.display = 'none';
    }
}

function updateCategoriesDatalist(categories) {
    const datalist = document.getElementById('categories-datalist');
    datalist.innerHTML = '';
    categories.forEach(cat => {
        const option = document.createElement('option');
        option.value = cat;
        datalist.appendChild(option);
    });
}

async function loadBlogPosts() {
    try {
        const response = await fetch('/api/blog');
        const data = await response.json();

        renderBlogPosts(data.posts);
    } catch (error) {
        console.error('Error loading blog posts:', error);
    }
}

function renderBlogPosts(posts) {
    const container = document.getElementById('blog-list');
    container.innerHTML = '';

    posts.forEach(post => {
        const postLink = document.createElement('a');
        postLink.className = 'blog-link';
        postLink.textContent = post.title;
        postLink.href = '#';
        postLink.onclick = (e) => {
            e.preventDefault();
            editBlogPost(post.slug);
        };
        container.appendChild(postLink);
    });
}

// ===== Show/Hide Editors =====

function showCreateProduct() {
    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('blog-editor').style.display = 'none';
    document.getElementById('product-editor').style.display = 'block';
    document.getElementById('product-editor-title').textContent = 'Create Product';
    document.getElementById('delete-product-btn').style.display = 'none';

    // Clear form
    document.getElementById('product-form').reset();
    document.getElementById('product-slug').value = '';
    document.getElementById('product-category').value = '';
    uploadedImages = [];
    renderImagesPreview();

    currentProduct = null;
}

function showCreateBlog() {
    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('product-editor').style.display = 'none';
    document.getElementById('blog-editor').style.display = 'block';
    document.getElementById('blog-editor-title').textContent = 'Create Blog Post';
    document.getElementById('delete-blog-btn').style.display = 'none';

    // Clear form
    document.getElementById('blog-form').reset();
    document.getElementById('blog-slug').value = '';
    document.getElementById('blog-date').value = new Date().toISOString().split('T')[0];

    currentBlogPost = null;
}

function closeEditor() {
    document.getElementById('product-editor').style.display = 'none';
    document.getElementById('blog-editor').style.display = 'none';
    document.getElementById('welcome-screen').style.display = 'block';
    document.getElementById('preview-container').innerHTML = '<p class="preview-placeholder">Preview will appear here...</p>';
}

// ===== Edit Product =====

async function editProduct(category, slug) {
    try {
        const response = await fetch(`/api/products/${category}/${slug}`);
        const data = await response.json();

        currentProduct = data.product;

        document.getElementById('welcome-screen').style.display = 'none';
        document.getElementById('blog-editor').style.display = 'none';
        document.getElementById('product-editor').style.display = 'block';
        document.getElementById('product-editor-title').textContent = 'Edit Product';
        document.getElementById('delete-product-btn').style.display = 'inline-block';

        // Fill form
        document.getElementById('product-slug').value = slug;
        document.getElementById('product-category').value = category;
        document.getElementById('product-title').value = currentProduct.title;
        document.getElementById('product-price').value = currentProduct.price;
        document.getElementById('product-category-select').value = currentProduct.category;
        document.getElementById('product-sku').value = currentProduct.sku || '';
        document.getElementById('product-in-stock').checked = currentProduct.in_stock;
        document.getElementById('product-description').value = currentProduct.description;
        document.getElementById('product-tags').value = currentProduct.tags.join('\n');

        // Fill new fields
        document.getElementById('product-pre-order').checked = currentProduct.is_pre_order || false;
        document.getElementById('product-available-date').value = currentProduct.available_date || '';
        document.getElementById('product-on-sale').checked = currentProduct.is_on_sale || false;
        document.getElementById('product-sale-price').value = currentProduct.sale_price || '';
        document.getElementById('product-new-arrival').checked = currentProduct.is_new_arrival || false;

        // Fill CSV fields
        document.getElementById('product-id').value = currentProduct.id || '';
        document.getElementById('product-cn-name').value = currentProduct.cn_name || '';
        document.getElementById('product-zhtw-name').value = currentProduct.zhtw_name || '';
        document.getElementById('product-series').value = currentProduct.series || '';
        document.getElementById('product-scale').value = currentProduct.scale || '';
        document.getElementById('product-size').value = currentProduct.size || '';
        document.getElementById('product-weight').value = currentProduct.weight || '';

        // Fill backend-only pricing fields
        document.getElementById('product-zhtw-price').value = currentProduct.zhtw_price || '';
        document.getElementById('product-cost').value = currentProduct.cost || '';
        document.getElementById('product-final-price').value = currentProduct.final_price || '';
        document.getElementById('product-cost-tw').value = currentProduct.cost_tw || '';

        // Calculate profit margin
        calculateProfitMargin();

        // Update conditional field visibility
        toggleAvailableDate();
        toggleSalePrice();

        uploadedImages = currentProduct.images || [];
        renderImagesPreview();

        updateProductPreview();
    } catch (error) {
        console.error('Error loading product:', error);
        alert('Error loading product');
    }
}

// ===== Edit Blog Post =====

async function editBlogPost(slug) {
    try {
        const response = await fetch(`/api/blog/${slug}`);
        const data = await response.json();

        currentBlogPost = data.post;

        document.getElementById('welcome-screen').style.display = 'none';
        document.getElementById('product-editor').style.display = 'none';
        document.getElementById('blog-editor').style.display = 'block';
        document.getElementById('blog-editor-title').textContent = 'Edit Blog Post';
        document.getElementById('delete-blog-btn').style.display = 'inline-block';

        // Fill form
        document.getElementById('blog-slug').value = slug;
        document.getElementById('blog-title').value = currentBlogPost.title;
        document.getElementById('blog-date').value = currentBlogPost.date;
        document.getElementById('blog-author').value = currentBlogPost.author || '';
        document.getElementById('blog-excerpt').value = currentBlogPost.excerpt || '';
        document.getElementById('blog-content').value = currentBlogPost.content;
        document.getElementById('blog-tags').value = Array.isArray(currentBlogPost.tags)
            ? currentBlogPost.tags.join(', ')
            : '';

        updateBlogPreview();
    } catch (error) {
        console.error('Error loading blog post:', error);
        alert('Error loading blog post');
    }
}

// ===== Form Handlers =====

function setupForms() {
    document.getElementById('product-form').addEventListener('submit', saveProduct);
    document.getElementById('blog-form').addEventListener('submit', saveBlogPost);
}

async function saveProduct(e) {
    e.preventDefault();

    const slug = document.getElementById('product-slug').value;
    const category = document.getElementById('product-category-select').value;

    const data = {
        title: document.getElementById('product-title').value,
        price: parseFloat(document.getElementById('product-price').value),
        category: category,
        sku: document.getElementById('product-sku').value,
        in_stock: document.getElementById('product-in-stock').checked,
        description: document.getElementById('product-description').value,
        tags: document.getElementById('product-tags').value.split('\n').filter(t => t.trim()),
        images: uploadedImages,
        is_pre_order: document.getElementById('product-pre-order').checked,
        available_date: document.getElementById('product-available-date').value,
        is_on_sale: document.getElementById('product-on-sale').checked,
        sale_price: parseFloat(document.getElementById('product-sale-price').value) || 0,
        is_new_arrival: document.getElementById('product-new-arrival').checked,
        // CSV fields
        id: document.getElementById('product-id').value,
        cn_name: document.getElementById('product-cn-name').value,
        zhtw_name: document.getElementById('product-zhtw-name').value,
        series: document.getElementById('product-series').value,
        scale: document.getElementById('product-scale').value,
        size: document.getElementById('product-size').value,
        weight: document.getElementById('product-weight').value,
        // Backend-only pricing fields
        zhtw_price: parseFloat(document.getElementById('product-zhtw-price').value) || 0,
        cost: parseFloat(document.getElementById('product-cost').value) || 0,
        final_price: parseFloat(document.getElementById('product-final-price').value) || 0,
        cost_tw: parseFloat(document.getElementById('product-cost-tw').value) || 0
    };

    try {
        let response;
        if (slug) {
            // Update existing
            response = await fetch(`/api/products/${document.getElementById('product-category').value}/${slug}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            // Create new
            response = await fetch('/api/products', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }

        const result = await response.json();

        if (result.success) {
            alert('Product saved successfully!');
            loadCategories();
            closeEditor();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error saving product:', error);
        alert('Error saving product');
    }
}

async function saveBlogPost(e) {
    e.preventDefault();

    const slug = document.getElementById('blog-slug').value;

    const tagsInput = document.getElementById('blog-tags').value;
    const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()) : [];

    const data = {
        title: document.getElementById('blog-title').value,
        date: document.getElementById('blog-date').value,
        author: document.getElementById('blog-author').value,
        excerpt: document.getElementById('blog-excerpt').value,
        content: document.getElementById('blog-content').value,
        tags: tags
    };

    try {
        let response;
        if (slug) {
            // Update existing
            response = await fetch(`/api/blog/${slug}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            // Create new
            response = await fetch('/api/blog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }

        const result = await response.json();

        if (result.success) {
            alert('Blog post saved successfully!');
            loadBlogPosts();
            closeEditor();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error saving blog post:', error);
        alert('Error saving blog post');
    }
}

// ===== Delete =====

async function deleteProduct() {
    if (!confirm('Are you sure you want to delete this product?')) return;

    const category = document.getElementById('product-category').value;
    const slug = document.getElementById('product-slug').value;

    try {
        const response = await fetch(`/api/products/${category}/${slug}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert('Product deleted successfully!');
            loadCategories();
            closeEditor();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error deleting product:', error);
        alert('Error deleting product');
    }
}

async function deleteBlogPost() {
    if (!confirm('Are you sure you want to delete this blog post?')) return;

    const slug = document.getElementById('blog-slug').value;

    try {
        const response = await fetch(`/api/blog/${slug}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert('Blog post deleted successfully!');
            loadBlogPosts();
            closeEditor();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        console.error('Error deleting blog post:', error);
        alert('Error deleting blog post');
    }
}

// ===== Image Upload =====

function setupImageUpload() {
    document.getElementById('image-upload').addEventListener('change', handleImageUpload);
}

async function handleImageUpload(e) {
    const files = e.target.files;
    if (!files.length) return;

    const category = document.getElementById('product-category-select').value;
    const title = document.getElementById('product-title').value;

    if (!category || !title) {
        alert('Please enter product name and category first');
        return;
    }

    const slug = slugify(title);

    for (let file of files) {
        const formData = new FormData();
        formData.append('image', file);
        formData.append('category', category);
        formData.append('slug', slug);

        try {
            const response = await fetch('/api/upload-image', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                uploadedImages.push(result.filename);
            } else {
                alert('Error uploading ' + file.name + ': ' + result.error);
            }
        } catch (error) {
            console.error('Error uploading image:', error);
            alert('Error uploading ' + file.name);
        }
    }

    renderImagesPreview();
    e.target.value = ''; // Reset input
}

function renderImagesPreview() {
    const container = document.getElementById('images-preview');
    container.innerHTML = '';

    uploadedImages.forEach((filename, index) => {
        const div = document.createElement('div');
        div.className = 'image-preview-item';
        div.draggable = true;
        div.dataset.index = index;

        // Add drag event listeners
        div.addEventListener('dragstart', handleDragStart);
        div.addEventListener('dragover', handleDragOver);
        div.addEventListener('drop', handleDrop);
        div.addEventListener('dragend', handleDragEnd);

        const category = document.getElementById('product-category-select').value;
        const slug = document.getElementById('product-slug').value ||
                      slugify(document.getElementById('product-title').value);
        const filePath = `/static/images/products/${category}/${slug}/${filename}`;

        // Check if it's a video
        const isVideo = /\.(mp4|mov|avi|webm)$/i.test(filename);

        if (isVideo) {
            const video = document.createElement('video');
            video.src = filePath;
            video.controls = false;
            video.style.width = '100%';
            video.style.height = '100%';
            video.style.objectFit = 'cover';
            div.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.src = filePath;
            div.appendChild(img);
        }

        const removeBtn = document.createElement('button');
        removeBtn.textContent = '×';
        removeBtn.className = 'remove-image';
        removeBtn.onclick = () => {
            uploadedImages.splice(index, 1);
            renderImagesPreview();
        };

        div.appendChild(removeBtn);
        container.appendChild(div);
    });
}

// Drag and drop handlers
let draggedIndex = null;

function handleDragStart(e) {
    draggedIndex = parseInt(e.currentTarget.dataset.index);
    e.currentTarget.style.opacity = '0.4';
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }

    const dropIndex = parseInt(e.currentTarget.dataset.index);

    if (draggedIndex !== dropIndex) {
        const draggedItem = uploadedImages[draggedIndex];
        uploadedImages.splice(draggedIndex, 1);
        uploadedImages.splice(dropIndex, 0, draggedItem);
        renderImagesPreview();
    }

    return false;
}

function handleDragEnd(e) {
    e.currentTarget.style.opacity = '1';
}

async function scanFolderForImages() {
    const category = document.getElementById('product-category-select').value;
    const slug = document.getElementById('product-slug').value ||
                  slugify(document.getElementById('product-title').value);

    if (!category || !slug) {
        alert('Please enter product name and category first');
        return;
    }

    try {
        const response = await fetch(`/api/scan-images?category=${encodeURIComponent(category)}&slug=${encodeURIComponent(slug)}`);
        const result = await response.json();

        if (result.success) {
            // Find new images that aren't in uploadedImages
            const newImages = result.images.filter(img => !uploadedImages.includes(img));

            if (newImages.length > 0) {
                // Add new images to the end
                uploadedImages.push(...newImages);
                renderImagesPreview();
                alert(`Added ${newImages.length} new image(s)/video(s) from folder`);
            } else {
                alert('No new images found in folder');
            }
        } else {
            alert('Error scanning folder: ' + result.error);
        }
    } catch (error) {
        console.error('Error scanning folder:', error);
        alert('Error scanning folder');
    }
}

// ===== Preview =====

function setupPreview() {
    // Update preview on input changes
    document.getElementById('product-description').addEventListener('input', updateProductPreview);
    document.getElementById('blog-content').addEventListener('input', updateBlogPreview);
}

function updateProductPreview() {
    const description = document.getElementById('product-description').value;
    const preview = document.getElementById('preview-container');

    if (description) {
        preview.innerHTML = `<div class="markdown-preview">${escapeHtml(description)}</div>`;
    } else {
        preview.innerHTML = '<p class="preview-placeholder">Enter description to see preview...</p>';
    }
}

function updateBlogPreview() {
    const content = document.getElementById('blog-content').value;
    const preview = document.getElementById('preview-container');

    if (content) {
        preview.innerHTML = `<div class="markdown-preview">${escapeHtml(content)}</div>`;
    } else {
        preview.innerHTML = '<p class="preview-placeholder">Enter content to see preview...</p>';
    }
}

// ===== Utilities =====

function slugify(text) {
    return text
        .toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/[\s_-]+/g, '-')
        .replace(/^-+|-+$/g, '');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
}

// ===== Conditional Field Visibility =====

function toggleAvailableDate() {
    const preOrderChecked = document.getElementById('product-pre-order').checked;
    const availableDateGroup = document.getElementById('available-date-group');
    availableDateGroup.style.display = preOrderChecked ? 'block' : 'none';
}

function toggleSalePrice() {
    const onSaleChecked = document.getElementById('product-on-sale').checked;
    const salePriceGroup = document.getElementById('sale-price-group');
    salePriceGroup.style.display = onSaleChecked ? 'block' : 'none';
}

// ===== Calculate Profit Margin =====

function calculateProfitMargin() {
    const finalPrice = parseFloat(document.getElementById('product-final-price').value) || 0;
    const cost = parseFloat(document.getElementById('product-cost').value) || 0;
    const profitMarginElement = document.getElementById('profit-margin');

    if (cost > 0) {
        const profit = finalPrice - cost;
        const margin = (profit / cost) * 100;
        profitMarginElement.textContent = `${margin.toFixed(2)}% (Profit: ${profit.toFixed(2)})`;

        // Color code based on margin
        if (margin > 150) {
            profitMarginElement.style.color = '#27ae60'; // Green
        } else if (margin > 100) {
            profitMarginElement.style.color = '#f39c12'; // Orange
        } else {
            profitMarginElement.style.color = '#e74c3c'; // Red
        }
    } else {
        profitMarginElement.textContent = '-';
        profitMarginElement.style.color = '#666';
    }
}

// Auto-calculate profit margin when relevant fields change
document.addEventListener('DOMContentLoaded', () => {
    const finalPriceInput = document.getElementById('product-final-price');
    const costInput = document.getElementById('product-cost');

    if (finalPriceInput && costInput) {
        finalPriceInput.addEventListener('input', calculateProfitMargin);
        costInput.addEventListener('input', calculateProfitMargin);
    }
});
