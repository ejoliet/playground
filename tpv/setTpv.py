# Purpose of this script
# Set TPV proj to PTF fits file which contain TPV coef
# Writes out a new file with updated projection 

# Import the astropy fits tools
from astropy.io import fits

# Open the file header for viewing and load the header
hdulist = fits.open('PTF-sample.fits')
header = hdulist[0].header

# Print the header keys from the file to the terminal
header.keys

# Modify the key called CTYPE to have a TPV instead
header['CTYPE1']=('RA---TPV','Modified to TPV for testing IRSA-1009')
header['CTYPE2']=('DEC---TPV','Modified to TPV for testing IRSA-1009')

# Add a new key to the header
header.set('EJOLIET','CHANGED ORIG FITS FILE TO TPV')

# Save the new file
hdulist.writeto('PTF-withTPV.fits')

# Make sure to close the file
hdulist.close()
