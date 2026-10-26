import io.github.reotech736.gotsuzuri.*;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.io.File;
import java.lang.reflect.*;
import java.util.*;

/** PC専用。現在のKotlinソースを別フォルダへコンパイルして色処理を共有する。 */
public class CandidateProbe {
    static Object get(Object object, String name) throws Exception {
        Method method = object.getClass().getDeclaredMethod(name);
        method.setAccessible(true);
        return method.invoke(object);
    }
    static double median(List<Double> values) {
        Collections.sort(values);
        return values.get(values.size() / 2);
    }
    public static void main(String[] args) throws Exception {
        System.setOut(new java.io.PrintStream(System.out, true, java.nio.charset.StandardCharsets.UTF_8));
        BufferedImage input = ImageIO.read(new File(args[0]));
        double scale = Math.min(1, 2048.0 / Math.max(input.getWidth(), input.getHeight()));
        BufferedImage image = new BufferedImage((int)Math.round(input.getWidth()*scale),
                (int)Math.round(input.getHeight()*scale), BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = image.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        graphics.drawImage(input, 0, 0, image.getWidth(), image.getHeight(), null);
        graphics.dispose();
        List<ImagePoint> corners = new ArrayList<>();
        for (int i=1; i<9; i+=2) corners.add(new ImagePoint(Double.parseDouble(args[i]), Double.parseDouble(args[i+1])));
        BoardProjection projection = BoardProjection.Companion.fromCorners(corners);
        PixelImage pixels = new PixelImage(image.getWidth(), image.getHeight(),
                image.getRGB(0,0,image.getWidth(),image.getHeight(),null,0,image.getWidth()));
        for (IntersectionCandidate c : StoneClassifier.INSTANCE.analyze(pixels, projection).getCandidates())
            System.out.println("B\t"+c.getColumn()+"\t"+c.getRow()+"\t"+c.getState());
        Class<?> patchClass = Class.forName("io.github.reotech736.gotsuzuri.StoneClassifier$Patch");
        Class<?> colorClass = Class.forName("io.github.reotech736.gotsuzuri.StoneClassifier$ColorSample");
        Method sample = StoneClassifier.class.getDeclaredMethod("samplePatch", PixelImage.class, BoardProjection.class, double.class, double.class);
        Method classify = StoneClassifier.class.getDeclaredMethod("classifySample", int.class,int.class,patchClass,colorClass);
        Method single = StoneClassifier.class.getDeclaredMethod("classifyPatch",int.class,int.class,List.class,colorClass);
        sample.setAccessible(true); classify.setAccessible(true); single.setAccessible(true);
        List<Double> lum = new ArrayList<>(), sat = new ArrayList<>(), ratio = new ArrayList<>();
        int total = 0;
        for (int r=0;r<19;r++) for (int c=0;c<19;c++) {
            Object patch = sample.invoke(StoneClassifier.INSTANCE,pixels,projection,(double)c,(double)r);
            for (Object color : (List<?>)get(patch,"getColors")) {
                total++;
                double l=(double)get(color,"getLuminance"), s=(double)get(color,"getSaturation"), b=(double)get(color,"getBlueRatio");
                if(l>=.12 && l<=.92 && s>=.18 && s<=.78 && b>=.18 && b<=.78) { lum.add(l);sat.add(s);ratio.add(b); }
            }
        }
        if (lum.size()<Math.max(100,total/5)) throw new IllegalStateException("No wood reference");
        Constructor<?> constructor = colorClass.getDeclaredConstructor(double.class,double.class,double.class);
        constructor.setAccessible(true);
        Object wood = constructor.newInstance(median(lum),median(sat),median(ratio));
        double dx=Double.parseDouble(args[9]), dy=Double.parseDouble(args[10]);
        // D: 交点によらない一定間隔の画像サンプル。Q: 空の根拠を調べる補正後位置。
        for (int mode=0;mode<2;mode++) {
            int count=mode==0?91:19;
            for(int r=0;r<count;r++) for(int c=0;c<count;c++) {
                double x=mode==0?c*.2:c+dx, y=mode==0?r*.2:r+dy;
                String state="UNKNOWN"; double support=0;
                if (x>=0 && x<=18 && y>=0 && y<=18) {
                    Object patch=sample.invoke(StoneClassifier.INSTANCE,pixels,projection,x,y);
                    if ((boolean)get(patch,"getEnoughPixels")) {
                        state=((IntersectionCandidate)classify.invoke(StoneClassifier.INSTANCE,0,0,patch,wood)).getState().name();
                        List<?> colors=(List<?>)get(patch,"getColors");
                        for(Object color:colors) if (((IntersectionCandidate)single.invoke(StoneClassifier.INSTANCE,0,0,List.of(color),wood)).getState().name().equals(state)) support++;
                        support/=colors.size();
                    }
                }
                System.out.println((mode==0?"D":"Q")+"\t"+(mode==0?x:c)+"\t"+(mode==0?y:r)+"\t"+state+"\t"+support);
            }
        }
    }
}
