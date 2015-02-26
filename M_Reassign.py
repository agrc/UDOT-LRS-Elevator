'''
Created on May 25, 2012

@author: kwalker
'''

'''
notes: 
-conversion to shape shortens long field names and that can mess stuff up.
'''

import arcpy, os, math
arcpy.env.overwriteOutput = True
#
###
#inRoutesFullPath = r'C:\KW_Working\Udot\CalibrationPointScript\CaliPointTesting.gdb\Route1534p'
inRoutesFullPath = arcpy.GetParameterAsText(0)
#referencePoints = r'C:\KW_Working\Udot\CalibrationPointScript\CaliPointTesting.gdb\Route1534refPoints'
referencePoints = arcpy.GetParameterAsText(1)

lrsSchemaTemplate = arcpy.GetParameterAsText(2)
#zSurfacePath = r"Database Connections\ConnectSGID10.sde\SGID10.RASTER.DEM_10METER"
zSurfacePath = arcpy.GetParameterAsText(3)
#outDirectoryWorkspace = r"C:\KW_Working\Udot\CalibrationPointScript\Test2865p2"#TODO make more relative
outDirectoryWorkspace = arcpy.GetParameterAsText(4)
#outFc = 'LRSTest7'#final route output will be named with a suffix given in createMZ_Route function
outFc = str(arcpy.GetParameterAsText(5))
###
#
#
tempOutsList = []

newOutputGDB = "LRS_RouteScript.gdb"

outFcMerge = outFc + "Merge"
newRtIdFieldName = "ScrptRtID" #Will be created and calculated to and ID number of
                                #the form "Route Number_Part Number" eg. "0039P_1"
finalOutPath = os.path.join(outDirectoryWorkspace, newOutputGDB, outFc)
                                
outFileGDB = arcpy.CreateFileGDB_management(outDirectoryWorkspace, newOutputGDB, "CURRENT")                                
arcpy.env.workspace = os.path.join(outDirectoryWorkspace, newOutputGDB)
arcpy.SetParameterAsText(6, outFc)#Output Parameter for script tool only
arcpy.SetParameterAsText(7, outFcMerge)#Output Parameter for script tool only

#Setting env fields to same values as SGID10.TRANSPORTATION.UDOTRoutes_LRS
arcpy.env.XYResolution = 0.01
arcpy.env.MResolution = 0.0005
arcpy.env.XYTolerance = 0.1
arcpy.env.MTolerance = 0.001
#arcpy.env.ZResolution = 0 #Changing the Z resolution changes the end value a little

routeFields = arcpy.ListFields(inRoutesFullPath)
for f in routeFields:
    if f.baseName == newRtIdFieldName:
        arcpy.AddError("Reserved Field: " + newRtIdFieldName + " already exists in input table")
    
if arcpy.CheckExtension("3D") != "Available":
    arcpy.AddError("3D Analyst: not available")
else:
    arcpy.AddMessage("3D analyst: " + str(arcpy.CheckExtension("3D")))

#Find Shape field name and spatial ref
inFcDesc = arcpy.Describe(inRoutesFullPath)
inFcShpField = inFcDesc.ShapeFieldName
inSpatialRef = inFcDesc.spatialReference
arcpy.AddMessage("Environment variables set")

def distanceFormula(x1 , y1, x2, y2):
    d = math.sqrt((math.pow((x2 - x1),2) + math.pow((y2 - y1),2)))
    return d
### End distanceFormula() ###
def lengthCalc3d(mzPnt1, mzPnt2):
    """3D line length calculation. Takes two arcpy Point objects  as input"""
    dist2dA = distanceFormula(mzPnt1.X, mzPnt1.Y, mzPnt2.X, mzPnt2.Y)
    zheightB = math.fabs(mzPnt1.Z - mzPnt2.Z)
    length3dC = math.sqrt((math.pow((dist2dA),2) + math.pow((zheightB),2)))
    return length3dC * 0.000621371192 #Conversion from meters to miles
### End lengthCalc3d() ###
def removeCurves (inFeatureFullPath, routeIdField):
    """Take and input feature class and Convert to a shapefile to remove curves"""
    tempFc = os.path.join(outDirectoryWorkspace, newOutputGDB, outFc + "TempCopy") 
    outShpFullName = os.path.join(outDirectoryWorkspace, outFc + "CurvRem.shp")
    tempOutsList.append(outShpFullName)#keep track of temp outputs for later deletion
    tempOutsList.append(tempFc)
    
    arcpy.CopyFeatures_management(inFeatureFullPath, tempFc)#Copy to feature class first to avoid GLOBALID issues
    arcpy.CopyFeatures_management(tempFc, outShpFullName)
    arcpy.AddField_management(outShpFullName, routeIdField, "TEXT", "", "", "20")
    arcpy.CalculateField_management(outShpFullName, routeIdField, '!DOT_RTNAME! + "_" + !DOT_RTPART!', "PYTHON_9.3")

    arcpy.AddMessage("Shapefile created to remove curves")
    return outShpFullName

def createMZ_Route (inCurvesRemovedPath, outFeatureClass, surfaceForZ, routeIdField):
    """Input the shapefile with curves removed, calc Z values and create the routes with temp M values that
    will be overridden"""
        
    extStatus = arcpy.CheckOutExtension("3D")
    arcpy.AddMessage("3D analyst: " + str(extStatus))
    outPolyLineZ = outFeatureClass + "LineZ"
    tempOutsList.append(outPolyLineZ)
    outRouteMZ = outFeatureClass
    rtPartNumField =  "PrtNum"
    rtPartCalcExp =  "!" + routeIdField + "![-1:]"
    
    arcpy.InterpolateShape_3d(surfaceForZ, inCurvesRemovedPath, outPolyLineZ, '', 1, '', True) 
    arcpy.AddMessage(arcpy.GetMessages())
    arcpy.CreateRoutes_lr(outPolyLineZ, routeIdField, outRouteMZ)
    arcpy.AddMessage(arcpy.GetMessages())
    arcpy.AddField_management(outRouteMZ, rtPartNumField, "SHORT")
    arcpy.CalculateField_management(outRouteMZ, rtPartNumField, rtPartCalcExp, "PYTHON_9.3")

    arcpy.AddMessage("Routes with Z values and M place holders have been created")
    extStatus = arcpy.CheckInExtension("3D")
    arcpy.AddMessage("3D analyst: " + str(extStatus))
    return [outRouteMZ, rtPartNumField]

def add3dLengthToM(routesMZ, routePartNumField):
    """Takes the output layer and the part field name from createMZ_Route as parameters. Calculates a 3D M value using distance
    between sequential Point objects and the differnce of those point's Z values"""
    
    routes = arcpy.UpdateCursor(routesMZ, "", "", "", newRtIdFieldName + " A")
    rtPrtLstPnt = arcpy.Point(0,0,0,0) 
                                        
    for rt in routes:
        print 'Route: ' + str(rt.getValue(newRtIdFieldName)) 
        rtShp = rt.getValue(inFcShpField)
        rtPartNum = rt.getValue(routePartNumField)
        newShpArray = arcpy.Array()
        previousPnt = arcpy.Point(0,0,0,0)   
        featurePartC = 0
        print "test"
        for part in rtShp:
            pntC = 0
            print "Feature Part: " + str(featurePartC)
            
            while pntC < part.count:#Loop through all points in current feature part Array object
                if pntC == 0:#testing to handle first points of feature part Array
                    if rtPartNum > 1 and featurePartC == 0:
                        if part.getObject(pntC).disjoint(rtPrtLstPnt):
                            part.getObject(pntC).M  = rtPrtLstPnt.M + 0.001
                        else:
                            part.getObject(pntC).M  = rtPrtLstPnt.M
                    else:
                        part.getObject(pntC).M = previousPnt.M
                        
                else:
                    mCalc = lengthCalc3d(previousPnt, part.getObject(pntC))
                    part.getObject(pntC).M = mCalc + previousPnt.M
                    
                previousPnt = part.getObject(pntC)#Assign the current point to the previous point for use in the next iteration 
                pntC += 1
            #End point while:
            newShpArray.add(part)
            featurePartC += 1
        #End part for:
        newShp = arcpy.Polyline(newShpArray, inSpatialRef)
        rt.setValue(inFcShpField, newShp)
        routes.updateRow(rt)
        rtPrtLstPnt = previousPnt
    arcpy.AddMessage("M values updated")
    
def routeFlipTemp(routesMZ, idField, refPointLayer):
    flipRtField = "FlipRt"
    arcpy.AddField_management(routesMZ, flipRtField, "SHORT")
    routesCursor = arcpy.UpdateCursor(routesMZ)
    
    for route in routesCursor:
        rtShp = route.getValue(inFcShpField)
        rtID = route.getValue(idField)
        print rtID
        rtEndPnt = rtShp.lastPoint
        #TODO if no ref points are found script errors out
        refPntCursor = arcpy.SearchCursor(refPointLayer, """ "LABEL" = '""" + rtID + "'")#Create reference point cursor limited by route ID of current route
        #Get the first ref point of the route and reset the closest point with it.
        #
        p = refPntCursor.next()
        closestRefPnt = p.getValue(inFcShpField).centroid
        closestDist = distanceFormula(rtEndPnt.X, rtEndPnt.Y, closestRefPnt.X, closestRefPnt.Y)   
        print "SP : " + str(p.CALPT_TYPE) + str(closestDist)
        closestType = str(p.CALPT_TYPE)
        ##
        for refPnt in refPntCursor:
            nextRefPnt = refPnt.getValue(inFcShpField).centroid
            nextDist = distanceFormula(rtEndPnt.X, rtEndPnt.Y, nextRefPnt.X, nextRefPnt.Y)
    
            if nextDist < closestDist:
                closestRefPnt = refPnt
                closestDist = nextDist
                closestType = str(refPnt.CALPT_TYPE)
                #print str(refPnt.CALPT_TYPE) + " c: " + str(closestDist)
                
            elif nextDist == closestDist:
                if str(refPnt.CALPT_TYPE).count("END") > 0 or str(refPnt.CALPT_TYPE).count("START") > 0:
                    closestRefPnt = refPnt
                    closestDist = nextDist
                    closestType = str(refPnt.CALPT_TYPE)
                    #print str(refPnt.CALPT_TYPE) + " c: " + str(closestDist)
                
#            else:
                #print str(refPnt.CALPT_TYPE) + " f: " + str(nextDist)
        
        #print  closestType + " final: " + str(closestDist) 
        #print
        if closestType.count("START") > 0: 
            route.setValue(flipRtField, 1)
            routesCursor.updateRow(route)

    del route
    del routesCursor 
    #Select by the flipRtField to flip routes that need it.
    arcpy.MakeFeatureLayer_management(routesMZ, "flipRts", '"' + flipRtField + '"' + " = 1 ")
    matchCount = int(arcpy.GetCount_management("flipRts").getOutput(0)) #temp
    arcpy.AddMessage("Attemping Flip of: " + str(matchCount))  
    arcpy.FlipLine_edit("flipRts")
    arcpy.AddMessage("Routes flipped: " + str(matchCount))

def routePartMerge (inputRoutesMZ, outGDB, outLayerName, lrsSchemaTemplate):
    """ Route part merging. Merges route parts into one feature. Populates LRS attributes."""
    arcpy.AddMessage("Merging route parts")
     
    inRouteLayer = inputRoutesMZ 
    outPath = outGDB
    outLayer = outLayerName
    outLayerTemplate = lrsSchemaTemplate
 
    inRouteDesc = arcpy.Describe(inRouteLayer)
    inFcShpField = inRouteDesc.ShapeFieldName
    inSpatialRef = inRouteDesc.spatialReference
    
    interstateRts = ["15", "70", "80", "84", "215"]
    usRts = ["6", "191", "89", "50", "89A", "491", "163", "40", "189", "90"]
    institutionalRts = ["284", "285", "286", "291", "292", "293", "294", "296", "298", "299", "303", "304", "309", "312", "317", "320"]
    
    print "settings complete"
    
    outLayer = arcpy.CreateFeatureclass_management (outPath, outLayer, "", outLayerTemplate, "ENABLED", "DISABLED", inSpatialRef)
    #Add route name field to input routes
    arcpy.AddField_management(inRouteLayer, "RtNumber", "TEXT", "", "", "15")
    #Calc new field to route name with direction 
    arcpy.CalculateField_management(inRouteLayer, "RtNumber", """!ScrptRtID!.split("_")[0]""", "PYTHON_9.3")
    #Build unique table base on route_Direction field
    arcpy.Frequency_analysis(inRouteLayer, os.path.join(outPath, "Freq_out"), "RtNumber")
    
    #init cursor for freq table
    frequencyCursor = arcpy.SearchCursor(os.path.join(outPath, "Freq_out"))
    #init cursors and combine route parts
    outFeatureCursor = arcpy.InsertCursor(outLayer)
    #iterate through unique table
    for uniqueRtNum in frequencyCursor:
        #print uniqueRtNum.getValue("RtNumber")
        
        inRtCursor = arcpy.SearchCursor(inRouteLayer, "\"RtNumber\" = '" + uniqueRtNum.getValue("RtNumber") + "'", "", "", "RtNumber A")#select by route_dir sort by part num
        
        outRow = outFeatureCursor.newRow()
        newShpArray = arcpy.Array()
        
        previousPnt = arcpy.Point(0,0,0,0) 
        featureCount = 0
        for routePart in inRtCursor:#feature
            #Get field data from route part and add it to out table
            if featureCount == 0:
                #print "set RtName: " + str(routePart.getValue("RtNumber"))
                outRow.setValue("LABEL", str(routePart.getValue("RtNumber")))
                outRow.setValue("RT_NAME", str(routePart.getValue("RtNumber"))[:4])
                outRow.setValue("RT_DIR", str(routePart.getValue("RtNumber"))[-1:])
                outRow.setValue("RT_TYPE", "M")
                #remove leading zeros from route nummber
                num = str(routePart.getValue("RtNumber"))[:4]
                while num.find("0") == 0:
                    num = num[1:]
                #Type labeling
                if interstateRts.count(num) > 0:
                    outRow.setValue("RT_MINDESC", "I " + num)
                    outRow.setValue("CARTO", "1")
                elif usRts.count(num) > 0:
                    outRow.setValue("RT_MINDESC", "US " + num)
                    outRow.setValue("CARTO", "2")
                elif institutionalRts.count(num) > 0:
                    outRow.setValue("RT_MINDESC", "SR " + num)
                    outRow.setValue("CARTO", "I")
                elif int(num) >= 1000:
                    outRow.setValue("RT_MINDESC", "FA " + num)
                    outRow.setValue("CARTO", "9")
                else:
                    outRow.setValue("RT_MINDESC", "SR " + num)
                    outRow.setValue("CARTO", "3")
    
            rtPartShape = routePart.SHAPE
            featurePartCount = 0
            for featurePart in rtPartShape:#feature part array
                    if featureCount == 0 and featurePartCount == 0:#first feature test
                        newShpArray.add(featurePart)
                    elif previousPnt.disjoint(featurePart.getObject(0)):
                        #print "prev: " + str(previousPnt.X) + " next: " + str(featurePart.getObject(0).X)
                        newShpArray.add(featurePart)
                    else:
                        featurePart.remove(0)
                        newShpArray.getObject(newShpArray.count - 1 ).extend(featurePart)
             
                    featurePartCount += 1
                    lastArrayAddedToNewShp = newShpArray.getObject(newShpArray.count - 1 )
                    previousPnt = lastArrayAddedToNewShp.getObject(lastArrayAddedToNewShp.count - 1 )
                    #print "FPC = " + str(featurePartCount)
                    
            featureCount += 1
            #print "FC = " + str(featureCount)
        
        #build new feature in out layer. 
        newShp = arcpy.Polyline(newShpArray, inSpatialRef)
        outRow.setValue(inFcShpField, newShp)
        outFeatureCursor.insertRow(outRow)
    try:
        del outRow
        del outFeatureCursor
        del inRtCursor
        del frequencyCursor
        arcpy.Delete_management(os.path.join(outPath, "Freq_out"))
    except:
        print "Some Temporary layers did not delete"
     
    print "Complete"  


curvesRemoved = removeCurves(inRoutesFullPath, newRtIdFieldName)
mz_RoutesReturn = createMZ_Route(curvesRemoved, outFc, zSurfacePath, newRtIdFieldName)
routeFlipTemp(mz_RoutesReturn[0], newRtIdFieldName, referencePoints)
add3dLengthToM(mz_RoutesReturn[0], mz_RoutesReturn[1])
routePartMerge(mz_RoutesReturn[0], os.path.join(outDirectoryWorkspace, newOutputGDB), outFcMerge, lrsSchemaTemplate)    
arcpy.AddMessage("Route creation completed")
arcpy.AddMessage("Final output routes located at: " + finalOutPath)

for layer in tempOutsList:
    try:
        arcpy.Delete_management(layer)
    except:
        arcpy.AddWarning("Some temp layers did not delete")