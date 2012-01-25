    //Extending the String type with a startsWith method to check if a string starts with a specific substring.
    if (typeof String.prototype.startsWith != 'function')
    {
        String.prototype.startsWith = function (str)
        {
	    return this.indexOf(str) == 0;
	};
    }

    //Extending the String type with an endsWith method to check if a string ends with a specific substring.
    if (typeof String.prototype.endsWith != 'function')
    {
	String.prototype.endsWith = function (str)
        {
	    retVal = false
	    if(this.indexOf(str) != -1)
	    if(this.indexOf(str) == this.length - str.length)
	        retVal = true
	    return retVal
	};
    }

    //Extending the Array type with a getUnique method to return the unique elements in the array.
    if (typeof Array.prototype.getUnique != 'function')
    {
        Array.prototype.getUnique = function ()
        {
            var o = new Object();
            var i, e;
            for (i = 0; i<this.length; i++) {o[this[i]] = 1};
            var a = new Array();
            for (e in o) {a.push (e)};
            return a;
        };
    }

    //Extending the Array type with a contains method to check if an element is present in the array.
    if (typeof Array.prototype.contains != 'function')
    {
        Array.prototype.contains = function (element)
        {
            var arrayLength = this.length;
            for(iterator = 0; iterator < arrayLength; iterator++)
                if(this[iterator] == element)
                    return true;
            return false;
        }
    }
