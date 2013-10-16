#!/usr/bin/python
# -*- coding: utf-8 -*-


import os, sys, glob
from shapely.wkt import dumps, loads
from shapely.ops import polygonize
try:
	from osgeo import ogr
except:
	import ogr
import pdb
	
'''
Procesa una lista de features de tipo LINESTRING y devuelve 1 feature de tipo Polygon.
No se hace ninguna validacion, se presupone que las features de entrada son de tipo
LINESTRING y que forman un area cerrada.
Ademas de las features de entrada, hay que pasar un objeto de tipo featureDefn para generar 
la plantilla de feature.
'''
def procesaLineaExterna(featuresExternas, featureDefn):
	#print "Procedemos a procesar las lineas externas"
	
	outFeature = ogr.Feature(featureDefn)
	geometry_out = None
	for inFeature in featuresExternas:
		geometry_in = inFeature.GetGeometryRef()
		if geometry_out is None:
			geometry_out = geometry_in
			geometry_out = ogr.ForceToMultiLineString(geometry_out)
		else:
			geometry_out = geometry_out.Union(geometry_in)
        
		
	geometryPoly = ogr.BuildPolygonFromEdges(geometry_out, dfTolerance = 0)
	#print 'Perimetro = ' + str(geometry_out.Length())
	#print 'Area = ' + str(geometryPoly.GetArea())
	
	outFeature.SetGeometry(geometryPoly)
	outFeature.SetField('rotulo', 'PARCELA')
	
	return outFeature
	

def procesaLineaInterna(featuresExternas, featuresInternas, featuresCentroide, featureDefn):
	#print "Procedemos a procesar las lineas internas"
	
	centroides = []
	for centroide in featuresCentroide:
		#obtenemos la altura y el rotulo del estilo de cada centroide
		for n in centroide.GetStyleString().split(','):
			if n.startswith('s'):
				altura = float(n.replace('s:', '').replace('g', ''))
			elif n.startswith('t'):
				rotulo = n.split('"')[1]
		punto = centroide.GetGeometryRef()
		x = punto.GetX()
		y = punto.GetY()
		longitudRotulo = len(rotulo)
		factor = 0.15 * (altura * 3.3333)
		desfaseX = longitudRotulo * factor - 0.05
		punto.SetPoint(point = 0, x = x + desfaseX, y = y - 0.20)
		
		centroides.append((rotulo, punto))
	
	featuresProceso = featuresExternas + featuresInternas
	
	outFeature = []
	if len(featuresProceso) > 1:
		geometry_out = None
		for inFeature in featuresProceso:
			geometry_in = inFeature.GetGeometryRef()
			if geometry_out is None:
				geometry_out = geometry_in
				geometry_out = ogr.ForceToMultiLineString(geometry_out)
			else:
				geometry_out = geometry_out.Union(geometry_in) 
		
		lineasInternasShapely = loads(geometry_out.ExportToWkt())
		polygonsShapely = polygonize(lineasInternasShapely)
	
		polygonGeom = []
		for polygon in polygonsShapely:
			polygonGeom.append(ogr.CreateGeometryFromWkt(dumps(polygon)))
		
		for pol in polygonGeom:
			for cen in centroides:
				if pol.Contains(cen[1]):
					feature = ogr.Feature(featureDefn)
					feature.SetGeometry(pol)
					feature.SetField('rotulo', cen[0])
					outFeature.append(feature.Clone())
					feature.Destroy()
	else:
		feature = ogr.Feature(featureDefn)
		geometryPoly = ogr.BuildPolygonFromEdges(ogr.ForceToMultiLineString(featuresProceso[0].GetGeometryRef()), dfTolerance = 0)
		feature.SetGeometry(geometryPoly)
		feature.SetField('rotulo', centroides[0][0])
		outFeature.append(feature.Clone())
		feature.Destroy()
	
	
	return outFeature
	
def procesaDxf(dxfFile, featureDefn):
	nombreDxf = os.path.splitext(os.path.basename(dxfFile))[0]
	driverIn = ogr.GetDriverByName('DXF')
	
	dataSource = driverIn.Open(dxfFile, 0)
	dataSource.ExecuteSQL("SELECT * FROM entities WHERE Layer = 'PG-LP' OR Layer = 'PG-LI' OR Layer = 'PG-AA'")
	layerIn = dataSource.GetLayer()
	
	totalRegistros = layerIn.GetFeatureCount()
	layerIn.ResetReading()
	inFeature = layerIn.GetNextFeature()
	
	cnt = 0
	featuresExternas = []
	featuresInternas = []
	featuresCentroide = []
	outFeature = []
	while inFeature:
		nombreCapa = inFeature.GetFieldAsString('Layer')
		if nombreCapa == 'PG-LP':
			featuresExternas.append(inFeature)
		elif nombreCapa == 'PG-LI':
			featuresInternas.append(inFeature)
		elif nombreCapa == 'PG-AA':
			featuresCentroide.append(inFeature)
		
		cnt = cnt + 1
		if cnt < totalRegistros: 
			inFeature = layerIn.GetNextFeature()
		else:
			break
	
	outFeature.append(procesaLineaExterna(featuresExternas, featureDefn))
	outFeature.extend(procesaLineaInterna(featuresExternas, featuresInternas, featuresCentroide, featureDefn))
	
	for feature in outFeature:
		feature.SetField('refcat', nombreDxf)
	
	dataSource.Destroy()
	
	return outFeature
	
def buscaDxf(baseDir):
	matches = []
	for root, dirnames, filenames in os.walk(baseDir):
		for filename in filenames:
			if os.path.splitext(filename)[1] == '.dxf':
				matches.append(os.path.join(root, filename))
	return matches
	
def main(baseDir, outFile):
	
	driverOut = ogr.GetDriverByName('ESRI Shapefile')
	dataSourceOut = driverOut.CreateDataSource(outFile)
	if os.path.exists(outFile):
		print "Ya existe un fichero " + outFile
		sys.exit(1)
	else:
		layerOut = dataSourceOut.CreateLayer('test', geom_type=ogr.wkbMultiPolygon)
		fieldRefCat = ogr.FieldDefn('refcat')
		layerOut.CreateField(fieldRefCat)
		fieldRotulo = ogr.FieldDefn('rotulo')
		layerOut.CreateField(fieldRotulo)
		featureDefn = layerOut.GetLayerDefn()
	
	ficheros = buscaDxf(baseDir)
	for dxf in ficheros:
		print '\nSe selecciona el fichero ' + dxf
		try:
			for feature in procesaDxf(dxf, featureDefn):
				layerOut.CreateFeature(feature)
		except:
			print "Error procesando el FXCC " + dxf
		
	dataSourceOut.Destroy()
	
		
if (len(sys.argv)< 3):
	print """
	Script para generar un shape de todos los fxcc de catastro procesados.
	Por cada fxcc procesado se generan dos tipos de poligonos, uno de toda 
	la parcela con el campo rotulo igual a PARCELA y el resto de poligonos representando
	la topologia del fxcc con el campo "rotulo" igual a la altura o cultivo de planta
	general

	Uso: fxcc2shp.py directorio_para_buscar_fxcc fichero_shp_resultado
	
"""
	sys.exit(2)
else:
	baseDir = sys.argv[1]
	outFile = sys.argv[2]
	main(baseDir, outFile)
	