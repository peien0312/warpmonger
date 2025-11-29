/**
 * Shopping Cart/List functionality using localStorage
 */

const Cart = {
    KEY: 'warpmonger_cart',

    // Get all items from cart
    getItems: function() {
        try {
            const data = localStorage.getItem(this.KEY);
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Error reading cart:', e);
            return [];
        }
    },

    // Save items to cart
    saveItems: function(items) {
        try {
            localStorage.setItem(this.KEY, JSON.stringify(items));
            this.updateBadge();
        } catch (e) {
            console.error('Error saving cart:', e);
        }
    },

    // Add item to cart (or increase quantity if exists)
    addItem: function(product, quantity) {
        quantity = parseInt(quantity) || 1;
        const items = this.getItems();

        // Check if item already exists
        const existingIndex = items.findIndex(function(item) {
            return item.category === product.category && item.slug === product.slug;
        });

        if (existingIndex >= 0) {
            // Update quantity
            items[existingIndex].quantity += quantity;
        } else {
            // Add new item
            items.push({
                category: product.category,
                slug: product.slug,
                title: product.title,
                price: parseFloat(product.price),
                image: product.image || '',
                quantity: quantity,
                inStock: product.inStock !== false,
                isPreOrder: product.isPreOrder === true
            });
        }

        this.saveItems(items);
        this.showToast('Added to list!');
        return true;
    },

    // Update item quantity
    updateQuantity: function(category, slug, quantity) {
        quantity = parseInt(quantity);
        if (quantity < 1) {
            return this.removeItem(category, slug);
        }

        const items = this.getItems();
        const index = items.findIndex(function(item) {
            return item.category === category && item.slug === slug;
        });

        if (index >= 0) {
            items[index].quantity = quantity;
            this.saveItems(items);
        }
    },

    // Remove item from cart
    removeItem: function(category, slug) {
        const items = this.getItems().filter(function(item) {
            return !(item.category === category && item.slug === slug);
        });
        this.saveItems(items);
    },

    // Clear all items
    clear: function() {
        localStorage.removeItem(this.KEY);
        this.updateBadge();
    },

    // Get total item count
    getCount: function() {
        const items = this.getItems();
        return items.reduce(function(sum, item) {
            return sum + item.quantity;
        }, 0);
    },

    // Get total price
    getTotal: function() {
        const items = this.getItems();
        return items.reduce(function(sum, item) {
            return sum + (item.price * item.quantity);
        }, 0);
    },

    // Update cart badge in header
    updateBadge: function() {
        const badge = document.getElementById('cart-badge');
        if (badge) {
            const count = this.getCount();
            badge.textContent = count;
            badge.style.display = count > 0 ? 'flex' : 'none';
        }
    },

    // Show toast notification
    showToast: function(message) {
        // Remove existing toast
        const existingToast = document.querySelector('.cart-toast');
        if (existingToast) {
            existingToast.remove();
        }

        // Create toast
        const toast = document.createElement('div');
        toast.className = 'cart-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        // Animate in
        setTimeout(function() {
            toast.classList.add('show');
        }, 10);

        // Remove after delay
        setTimeout(function() {
            toast.classList.remove('show');
            setTimeout(function() {
                toast.remove();
            }, 300);
        }, 2000);
    },

    // Format cart as text for sharing
    formatAsText: function() {
        const items = this.getItems();
        if (items.length === 0) return 'Shopping list is empty';

        let text = 'Shopping List:\n\n';
        items.forEach(function(item, index) {
            var statusPrefix = '';
            if (item.inStock === false) {
                statusPrefix = '[Out of Stock] ';
            } else if (item.isPreOrder === true) {
                statusPrefix = '[Pre-Order] ';
            }
            text += (index + 1) + '. ' + statusPrefix + item.title + '\n';
            text += '   Qty: ' + item.quantity + ' x $' + item.price.toFixed(2) + ' = $' + (item.quantity * item.price).toFixed(2) + '\n';
            text += '   Link: ' + window.location.origin + '/products/' + item.category + '/' + item.slug + '\n\n';
        });
        text += 'Total: $' + this.getTotal().toFixed(2);
        return text;
    }
};

// Initialize badge on page load
document.addEventListener('DOMContentLoaded', function() {
    Cart.updateBadge();
});
