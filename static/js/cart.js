/**
 * Shopping Cart/List functionality using localStorage
 */

const Cart = {
    _getLocale: function() {
        return (document.body && document.body.getAttribute('data-locale')) || 'en';
    },
    _getKey: function() {
        return this._getLocale() === 'zhtw' ? 'warpmonger_cart_zhtw' : 'warpmonger_cart';
    },

    // Get all items from cart
    getItems: function() {
        try {
            const data = localStorage.getItem(this._getKey());
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Error reading cart:', e);
            return [];
        }
    },

    // Save items to cart
    saveItems: function(items) {
        try {
            localStorage.setItem(this._getKey(), JSON.stringify(items));
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
        this.showToast(this._getLocale() === 'zhtw' ? '已加入清單！' : 'Added to list!');
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
        localStorage.removeItem(this._getKey());
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
        const isZhtw = this._getLocale() === 'zhtw';
        const urlPrefix = isZhtw ? '/zhtw' : '';

        if (items.length === 0) return isZhtw ? '購物清單是空的' : 'Shopping list is empty';

        let text = (isZhtw ? '購物清單：\n\n' : 'Shopping List:\n\n');
        items.forEach(function(item, index) {
            var statusPrefix = '';
            if (item.inStock === false) {
                statusPrefix = isZhtw ? '[缺貨] ' : '[Out of Stock] ';
            } else if (item.isPreOrder === true) {
                statusPrefix = isZhtw ? '[預購] ' : '[Pre-Order] ';
            }
            text += (index + 1) + '. ' + statusPrefix + item.title + '\n';
            if (isZhtw) {
                text += '   ' + item.quantity + ' x NT$' + Math.round(item.price).toLocaleString() + ' = NT$' + Math.round(item.quantity * item.price).toLocaleString() + '\n';
            } else {
                text += '   Qty: ' + item.quantity + ' x $' + item.price.toFixed(2) + ' = $' + (item.quantity * item.price).toFixed(2) + '\n';
            }
            text += '   Link: ' + window.location.origin + urlPrefix + '/products/' + item.category + '/' + item.slug + '\n\n';
        });
        if (isZhtw) {
            text += '合計: NT$' + Math.round(this.getTotal()).toLocaleString();
        } else {
            text += 'Total: $' + this.getTotal().toFixed(2);
        }
        return text;
    }
};

// Initialize badge on page load
document.addEventListener('DOMContentLoaded', function() {
    Cart.updateBadge();
});
